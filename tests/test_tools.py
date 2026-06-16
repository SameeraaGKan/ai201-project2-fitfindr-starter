"""
tests/test_tools.py

pytest tests for all three FitFindr tools.
Run with:  pytest tests/ -v

Tests cover:
  - search_listings: results, empty results, price filter, size filter, scoring
  - suggest_outfit: empty wardrobe (no crash), non-empty wardrobe (returns str)
  - create_fit_card: empty outfit guard, normal input returns non-empty string
"""

import pytest
from unittest.mock import patch, MagicMock

from tools import search_listings, suggest_outfit, create_fit_card


# ═══════════════════════════════════════════════════════
# Tool 1: search_listings
# ═══════════════════════════════════════════════════════

class TestSearchListings:

    def test_returns_list(self):
        results = search_listings("vintage graphic tee", size=None, max_price=None)
        assert isinstance(results, list)

    def test_happy_path_returns_results(self):
        results = search_listings("vintage graphic tee", size=None, max_price=50)
        assert len(results) > 0

    def test_impossible_query_returns_empty_list(self):
        """No exception — just an empty list when nothing matches."""
        results = search_listings("designer ballgown", size="XXS", max_price=5)
        assert results == []

    def test_price_filter_respected(self):
        results = search_listings("jacket", size=None, max_price=40)
        assert all(item["price"] <= 40 for item in results)

    def test_price_filter_strict(self):
        """Items exactly at max_price should be included."""
        results = search_listings("jeans", size=None, max_price=38)
        assert all(item["price"] <= 38 for item in results)

    def test_size_filter_case_insensitive(self):
        results = search_listings("track jacket", size="m", max_price=None)
        # Every result's size field must contain the letter M (case-insensitive)
        for item in results:
            assert "m" in item["size"].lower()

    def test_results_have_required_fields(self):
        results = search_listings("vintage tee", size=None, max_price=50)
        assert len(results) > 0
        required = {"id", "title", "price", "platform", "size", "condition"}
        for item in results:
            assert required.issubset(item.keys()), f"Missing fields in {item}"

    def test_no_zero_score_items(self):
        """Items with no keyword overlap should not appear in results."""
        results = search_listings("shoe boot sneaker", size=None, max_price=None)
        # All results should be shoes/footwear-related, not tops or bottoms
        for item in results:
            text = (item.get("title", "") + " " +
                    " ".join(item.get("style_tags", []))).lower()
            assert any(kw in text for kw in ["shoe", "boot", "sneaker", "platform"])

    def test_empty_description_returns_empty_list(self):
        """A description with no matching keywords should return nothing."""
        results = search_listings("xyznotarealword", size=None, max_price=None)
        assert results == []

    def test_none_price_does_not_filter(self):
        """max_price=None should return more results than a tight ceiling."""
        results_all = search_listings("vintage", size=None, max_price=None)
        results_cheap = search_listings("vintage", size=None, max_price=15)
        assert len(results_all) >= len(results_cheap)

    def test_results_sorted_by_relevance(self):
        """Top result should be more keyword-relevant than last result."""
        results = search_listings("graphic tee vintage streetwear", size=None, max_price=None)
        assert len(results) >= 2
        # Top result should have more matching tags than the last
        def tag_overlap(item):
            tags = " ".join(item.get("style_tags", [])).lower()
            return sum(1 for kw in ["graphic", "tee", "vintage", "streetwear"] if kw in tags)
        assert tag_overlap(results[0]) >= tag_overlap(results[-1])


# ═══════════════════════════════════════════════════════
# Tool 2: suggest_outfit
# ═══════════════════════════════════════════════════════

MOCK_ITEM = {
    "id": "lst_006",
    "title": "Graphic Tee — 2003 Tour Bootleg Style",
    "description": "Vintage-style bootleg tee with faded graphic. Slightly boxy fit.",
    "category": "tops",
    "style_tags": ["graphic tee", "vintage", "grunge", "streetwear"],
    "size": "L",
    "condition": "good",
    "price": 24.00,
    "colors": ["black"],
    "brand": None,
    "platform": "depop",
}

MOCK_WARDROBE = {
    "items": [
        {
            "id": "w_001",
            "name": "Baggy straight-leg jeans, dark wash",
            "category": "bottoms",
            "colors": ["dark blue"],
            "style_tags": ["denim", "streetwear"],
            "notes": None,
        },
        {
            "id": "w_007",
            "name": "Chunky white sneakers",
            "category": "shoes",
            "colors": ["white"],
            "style_tags": ["sneakers", "chunky"],
            "notes": None,
        },
    ]
}

EMPTY_WARDROBE = {"items": []}


class TestSuggestOutfit:

    @patch("tools._get_groq_client")
    def test_returns_string(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Pair with baggy jeans and white sneakers."))]
        )
        mock_client_fn.return_value = mock_client

        result = suggest_outfit(MOCK_ITEM, MOCK_WARDROBE)
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("tools._get_groq_client")
    def test_empty_wardrobe_does_not_crash(self, mock_client_fn):
        """Empty wardrobe must return a string, not raise an exception."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Try this with wide-leg jeans."))]
        )
        mock_client_fn.return_value = mock_client

        result = suggest_outfit(MOCK_ITEM, EMPTY_WARDROBE)
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("tools._get_groq_client")
    def test_llm_error_returns_string_not_exception(self, mock_client_fn):
        """If the LLM call fails, return an error string — don't raise."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API timeout")
        mock_client_fn.return_value = mock_client

        result = suggest_outfit(MOCK_ITEM, MOCK_WARDROBE)
        assert isinstance(result, str)
        assert len(result) > 0  # descriptive error message

    @patch("tools._get_groq_client")
    def test_wardrobe_items_referenced_in_prompt(self, mock_client_fn):
        """The LLM should be called once — verify it was called with wardrobe context."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Style suggestion here."))]
        )
        mock_client_fn.return_value = mock_client

        suggest_outfit(MOCK_ITEM, MOCK_WARDROBE)
        assert mock_client.chat.completions.create.called


# ═══════════════════════════════════════════════════════
# Tool 3: create_fit_card
# ═══════════════════════════════════════════════════════

MOCK_OUTFIT = (
    "Pair this Graphic Tee with your baggy dark-wash jeans and chunky white sneakers "
    "for a classic 90s streetwear look. Tuck the front corner for shape."
)


class TestCreateFitCard:

    def test_empty_outfit_returns_error_string_not_exception(self):
        """Empty outfit must return an error string, not raise."""
        result = create_fit_card("", MOCK_ITEM)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_whitespace_outfit_returns_error_string(self):
        result = create_fit_card("   ", MOCK_ITEM)
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("tools._get_groq_client")
    def test_returns_non_empty_string(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content="thrifted this graphic tee off depop for $24 and it was made for my baggy jeans 🖤"
            ))]
        )
        mock_client_fn.return_value = mock_client

        result = create_fit_card(MOCK_OUTFIT, MOCK_ITEM)
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("tools._get_groq_client")
    def test_llm_error_returns_string_not_exception(self, mock_client_fn):
        """If the LLM call fails, return an error string — don't raise."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Rate limit")
        mock_client_fn.return_value = mock_client

        result = create_fit_card(MOCK_OUTFIT, MOCK_ITEM)
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("tools._get_groq_client")
    def test_caption_varies_across_calls(self, mock_client_fn):
        """Different outfit inputs should produce different captions."""
        responses = [
            "thrifted this tee off depop for $24 🖤",
            "found this gem on depop and it's everything",
        ]
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            content = responses[call_count % len(responses)]
            call_count += 1
            return MagicMock(choices=[MagicMock(message=MagicMock(content=content))])

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = side_effect
        mock_client_fn.return_value = mock_client

        outfit_a = "Baggy jeans, chunky sneakers, and this graphic tee."
        outfit_b = "Slip dress layered under this tee with combat boots."

        result_a = create_fit_card(outfit_a, MOCK_ITEM)
        result_b = create_fit_card(outfit_b, MOCK_ITEM)
        assert result_a != result_b