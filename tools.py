"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for.
        size:        Size string to filter by, or None to skip size filtering.
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.
    """
    try:
        listings = load_listings()
    except Exception:
        return []

    # Step 1: apply hard filters (price and size)
    filtered = []
    for item in listings:
        if max_price is not None and item.get("price", 0) > max_price:
            continue
        if size is not None:
            item_size = item.get("size", "").lower()
            if size.lower() not in item_size:
                continue
        filtered.append(item)

    # Step 2: score by keyword overlap with description
    keywords = set(description.lower().split())

    def score(item):
        text = " ".join([
            item.get("title", ""),
            item.get("description", ""),
            item.get("category", ""),
            " ".join(item.get("style_tags", [])),
            " ".join(item.get("colors", [])),
            item.get("brand", "") or "",
        ]).lower()
        return sum(1 for kw in keywords if kw in text)

    scored = [(item, score(item)) for item in filtered]

    # Step 3: drop items with zero keyword match
    scored = [(item, s) for item, s in scored if s > 0]

    # Step 4: sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)

    return [item for item, _ in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key. May be empty.

    Returns:
        A non-empty string with outfit suggestions. If wardrobe is empty,
        returns general styling advice rather than raising an exception.
    """
    try:
        client = _get_groq_client()
    except ValueError as e:
        return f"Error: {e}"

    item_summary = (
        f"'{new_item.get('title', 'Unknown item')}' — "
        f"{new_item.get('description', '')} "
        f"(${new_item.get('price', '?')}, {new_item.get('platform', '?')}, "
        f"size {new_item.get('size', '?')}, condition: {new_item.get('condition', '?')}). "
        f"Style tags: {', '.join(new_item.get('style_tags', []))}. "
        f"Colors: {', '.join(new_item.get('colors', []))}."
    )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        prompt = (
            f"A thrift shopper is considering buying: {item_summary}\n\n"
            "They haven't described their existing wardrobe yet. Give them 1–2 specific, "
            "practical outfit ideas for this piece — mention what kinds of bottoms, shoes, "
            "and layers would work well with it. Be specific about silhouettes, colors, and "
            "vibes. Keep it casual and direct, like advice from a stylish friend."
        )
    else:
        wardrobe_text = "\n".join(
            f"- {w.get('name', 'item')} ({', '.join(w.get('colors', []))})"
            f"{' — ' + w.get('notes') if w.get('notes') else ''}"
            for w in wardrobe_items
        )
        prompt = (
            f"A thrift shopper is considering buying: {item_summary}\n\n"
            f"Here's what they already own:\n{wardrobe_text}\n\n"
            "Suggest 1–2 complete outfit combinations using the new thrifted item and specific "
            "pieces from their wardrobe above. Name the exact wardrobe pieces. Be specific about "
            "silhouette, vibe, and how to wear it. Keep it casual and friendly, like advice from "
            "a stylish friend who knows their closet."
        )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Couldn't generate outfit suggestions right now ({e}). Try again in a moment."


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence caption string. If outfit is empty, returns an
        error message string — does NOT raise an exception.
    """
    if not outfit or not outfit.strip():
        return (
            "Couldn't generate a fit card — outfit description was empty. "
            "Make sure suggest_outfit ran successfully before calling this tool."
        )

    title = new_item.get("title", "this thrifted piece")
    price = new_item.get("price", "?")
    platform = new_item.get("platform", "a thrift platform")
    colors = ", ".join(new_item.get("colors", []))
    tags = ", ".join(new_item.get("style_tags", []))

    prompt = (
        f"Write a 2–4 sentence Instagram/TikTok OOTD caption for this thrifted outfit.\n\n"
        f"The thrifted item: {title}, ${price} from {platform}. Colors: {colors}. "
        f"Vibes: {tags}.\n\n"
        f"The full outfit: {outfit}\n\n"
        "Rules: sound like a real person posting their outfit, not a product description. "
        "Mention the item name, price, and platform naturally (once each). "
        "Capture the outfit vibe in specific terms. Use casual language. "
        "One or two relevant emojis max. Do not use hashtags. "
        "Make it feel authentic and personal, not like an ad."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=1.0,  # higher temp = more varied captions
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return (
            f"Couldn't generate a fit card right now ({e}). "
            "The outfit suggestion was saved — try again in a moment."
        )