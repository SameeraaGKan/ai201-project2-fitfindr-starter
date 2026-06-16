"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from tools import search_listings, suggest_outfit, create_fit_card

load_dotenv()


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query.

    Strategy: regex for price and size (fast, reliable), then use the
    remaining text as the description. Falls back to the full query as
    description if nothing is extracted.

    Returns:
        dict with keys: description (str), size (str|None), max_price (float|None)
    """
    text = query.strip()

    # Extract price ceiling — matches "under $30", "under 30", "< $30", "max $30", "$30 or less"
    price_patterns = [
        r"under\s*\$?([\d.]+)",
        r"less\s+than\s*\$?([\d.]+)",
        r"max(?:imum)?\s*\$?([\d.]+)",
        r"\$?([\d.]+)\s+or\s+less",
        r"<\s*\$?([\d.]+)",
        r"up\s+to\s*\$?([\d.]+)",
        r"\$?([\d.]+)\s+max",
    ]
    max_price = None
    for pattern in price_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            max_price = float(match.group(1))
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
            break

    # Extract size — matches "size M", "in M", "XS", "W30", "US 8", etc.
    size_patterns = [
        r"\bsize\s+([A-Z]{1,3}(?:\/[A-Z]{1,3})?)\b",
        r"\bin\s+(?:a\s+)?size\s+([A-Z]{1,3})\b",
        r"\b(XXS|XS|S|M|L|XL|XXL|XXXL)\b",
        r"\b(W\d{2}(?:\s+L\d{2})?)\b",
        r"\b(US\s*\d+(?:\.\d+)?)\b",
        r"\b(UK\s*\d+)\b",
        r"\bone\s+size\b",
    ]
    size = None
    for pattern in size_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            size = match.group(1) if match.lastindex else match.group(0)
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
            break

    # Clean up the remaining text as the description
    description = re.sub(r"\s{2,}", " ", text).strip(" ,.-")
    if not description:
        description = query  # fall back to full query

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Planning loop logic:
        1. Parse the query → extract description, size, max_price
        2. Call search_listings() with parsed params
           → if empty: set error, return early (do NOT call suggest_outfit)
           → if results: pick top result as selected_item
        3. Call suggest_outfit(selected_item, wardrobe)
           → if empty string returned: set error, return early
        4. Call create_fit_card(outfit_suggestion, selected_item)
        5. Return session

    Args:
        query:    Natural language user request
        wardrobe: User's wardrobe dict

    Returns:
        Session dict. Check session["error"] first — if not None, the
        interaction ended early and outfit_suggestion / fit_card will be None.
    """
    session = _new_session(query, wardrobe)

    # ── Step 1: Parse the query ───────────────────────────────────────────────
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # ── Step 2: Search listings ───────────────────────────────────────────────
    results = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    session["search_results"] = results

    if not results:
        filters_used = []
        if parsed["size"]:
            filters_used.append(f"size {parsed['size']}")
        if parsed["max_price"] is not None:
            filters_used.append(f"under ${parsed['max_price']:.0f}")
        filter_note = f" with filters: {', '.join(filters_used)}" if filters_used else ""

        session["error"] = (
            f"No listings found for \"{parsed['description']}\"{filter_note}. "
            "Try broadening your search — remove the size or price filter, "
            "or use different keywords (e.g. 'tee' instead of 'graphic tee')."
        )
        return session

    # ── Step 3: Select top result ─────────────────────────────────────────────
    session["selected_item"] = results[0]

    # ── Step 4: Suggest outfit ────────────────────────────────────────────────
    outfit = suggest_outfit(session["selected_item"], wardrobe)
    session["outfit_suggestion"] = outfit

    if not outfit or outfit.startswith("Error:") or not outfit.strip():
        session["error"] = (
            "Found a great listing but couldn't generate outfit suggestions right now. "
            f"The item was: {session['selected_item']['title']}. Try again in a moment."
        )
        return session

    # ── Step 5: Create fit card ───────────────────────────────────────────────
    fit_card = create_fit_card(outfit, session["selected_item"])
    session["fit_card"] = fit_card

    # ── Step 6: Return completed session ─────────────────────────────────────
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: vintage graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        item = session["selected_item"]
        print(f"Found: {item['title']} — ${item['price']} on {item['platform']}")
        print(f"\nOutfit:\n{session['outfit_suggestion']}")
        print(f"\nFit card:\n{session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")

    print("\n\n=== Empty wardrobe path ===\n")
    session3 = run_agent(
        query="90s track jacket size M",
        wardrobe=get_empty_wardrobe(),
    )
    if session3["error"]:
        print(f"Error: {session3['error']}")
    else:
        print(f"Found: {session3['selected_item']['title']}")
        print(f"\nOutfit:\n{session3['outfit_suggestion']}")
        print(f"\nFit card:\n{session3['fit_card']}")