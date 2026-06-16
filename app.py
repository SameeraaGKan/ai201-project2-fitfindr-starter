"""
app.py

Gradio interface for FitFindr. Run with:
    python app.py

Then open the URL shown in your terminal (usually http://localhost:7860).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Args:
        user_query:      The text the user typed into the search box.
        wardrobe_choice: Either "Example wardrobe" or "Empty wardrobe (new user)".

    Returns:
        (listing_text, outfit_suggestion, fit_card) — one string per output panel.
    """
    # Step 1: Guard against empty query
    if not user_query or not user_query.strip():
        return "Please enter a search query to get started.", "", ""

    # Step 2: Select wardrobe
    wardrobe = (
        get_empty_wardrobe()
        if wardrobe_choice == "Empty wardrobe (new user)"
        else get_example_wardrobe()
    )

    # Step 3: Run the agent
    session = run_agent(query=user_query, wardrobe=wardrobe)

    # Step 4: Handle early termination (search found nothing, or LLM error)
    if session["error"]:
        return session["error"], "", ""

    # Step 5: Format the listing panel
    item = session["selected_item"]
    all_results = session["search_results"]

    listing_text = (
        f"✅ Found {len(all_results)} match{'es' if len(all_results) != 1 else ''} "
        f"— showing top result:\n\n"
        f"📌 {item['title']}\n"
        f"💰 ${item['price']:.2f}  |  🏷️ {item['platform'].title()}  |  📏 Size: {item['size']}\n"
        f"🔖 Condition: {item['condition'].title()}\n\n"
        f"{item['description']}\n\n"
        f"Tags: {', '.join(item.get('style_tags', []))}\n"
        f"Colors: {', '.join(item.get('colors', []))}"
    )
    if item.get("brand"):
        listing_text += f"\nBrand: {item['brand']}"

    return listing_text, session["outfit_suggestion"], session["fit_card"]


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]

def build_interface():
    with gr.Blocks(title="FitFindr", theme=gr.themes.Soft()) as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=8,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=8,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=8,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()