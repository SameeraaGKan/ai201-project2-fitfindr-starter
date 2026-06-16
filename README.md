# FitFindr 🛍️

A multi-tool AI agent that helps you find secondhand pieces and figure out how to wear them. Describe what you're thrifting for, and FitFindr searches the listings, builds outfit ideas from your existing wardrobe, and generates a shareable caption — all in one flow.

---

## Setup

```bash
# 1. Clone the repo and create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Mac/Linux
source .venv/Scripts/activate    # Windows (Git Bash)

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your Groq API key (free at console.groq.com)
echo "GROQ_API_KEY=your_key_here" > .env

# 4. Run the app
python app.py
```

Open `http://localhost:7860` (or the URL shown in your terminal).

---

## Tool Inventory

### `search_listings(description, size, max_price)`

Searches the mock listings dataset for items matching the user's natural language description.

| Parameter | Type | Purpose |
|-----------|------|---------|
| `description` | `str` | Keywords describing the item (e.g. "vintage graphic tee") |
| `size` | `str \| None` | Size filter — case-insensitive substring match (e.g. "M", "W30"). `None` skips. |
| `max_price` | `float \| None` | Price ceiling inclusive. `None` skips. |

**Returns:** `list[dict]` — matching listing dicts sorted by relevance score (highest first), or `[]` if nothing matches. Each dict has: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str or None), `platform`.

---

### `suggest_outfit(new_item, wardrobe)`

Uses the Groq LLM to suggest 1–2 outfit combinations based on the thrifted item and the user's existing wardrobe.

| Parameter | Type | Purpose |
|-----------|------|---------|
| `new_item` | `dict` | A full listing dict — the top result from `search_listings` |
| `wardrobe` | `dict` | Dict with an `items` key containing wardrobe item dicts. May be empty. |

**Returns:** `str` — outfit suggestion text. If `wardrobe["items"]` is empty, returns general styling advice rather than specific combinations.

---

### `create_fit_card(outfit, new_item)`

Uses the Groq LLM to generate a 2–4 sentence Instagram/TikTok-style OOTD caption. Temperature is set to 1.0 so output varies meaningfully across calls.

| Parameter | Type | Purpose |
|-----------|------|---------|
| `outfit` | `str` | Outfit suggestion string from `suggest_outfit`. Must be non-empty. |
| `new_item` | `dict` | Listing dict — used for item name, price, and platform in the caption |

**Returns:** `str` — a casual, authentic-sounding caption mentioning the item, price, and platform once each. Returns an error message string if `outfit` is empty.

---

## How the Planning Loop Works

The agent runs a **sequential conditional loop** — it selects which tools to call based on what was returned, rather than calling all three unconditionally.

```
1. Parse the query (regex) → extract description, size, max_price

2. Call search_listings()
   → No results? Set error message, return early. suggest_outfit never called.
   → Results found? Pick top result as selected_item, continue.

3. Call suggest_outfit(selected_item, wardrobe)
   → Empty/error string? Set error message, return early. create_fit_card never called.
   → Valid suggestion? Store in session, continue.

4. Call create_fit_card(outfit_suggestion, selected_item)
   → Store caption in session.

5. Return session.
```

The key behavior: if `search_listings` returns nothing, the loop ends immediately. `suggest_outfit` is never called with empty input, and `create_fit_card` is never called without an outfit to work from. The agent's path through the tools depends entirely on what each step returns.

---

## State Management

All state lives in a single `session` dict created at the start of each `run_agent()` call. Tools do not share state through globals — everything flows through the session.

| Key | Populated by | Used by |
|-----|-------------|---------|
| `query` | `run_agent` (init) | Error messages |
| `parsed` | `_parse_query()` | `search_listings` args |
| `search_results` | `search_listings` | Picking `selected_item` |
| `selected_item` | Planning loop (step 3) | `suggest_outfit`, `create_fit_card`, UI panel |
| `wardrobe` | `run_agent` (init) | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card`, UI panel |
| `fit_card` | `create_fit_card` | UI panel |
| `error` | Any step on failure | UI panel; stops further tool calls |

`app.py` reads from the session at the end — it never re-prompts the user or reconstructs data that was already computed.

---

## Error Handling

### `search_listings` — no results
If the search returns an empty list, the agent sets a descriptive error message naming which filters were applied and what the user can try differently:

> *"No listings found for 'designer ballgown' with filters: size XXS, under $5. Try broadening your search — remove the size or price filter, or use different keywords (e.g. 'tee' instead of 'graphic tee')."*

The planning loop returns immediately after setting this error. `suggest_outfit` is never called with empty input.

**Tested by running:**
```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
# Output: []  ← no exception raised
```

---

### `suggest_outfit` — empty wardrobe
Instead of crashing or returning an empty string, the tool detects `wardrobe["items"] == []` and switches to a general styling prompt. The LLM gives advice about what silhouettes, colors, and shoe types pair well with the item — useful even without a specific wardrobe to reference.

**Tested by running:**
```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
# Output: general styling advice string — no exception
```

---

### `create_fit_card` — empty outfit input
The function guards against an empty or whitespace-only `outfit` string before making any LLM call. If the guard triggers, it returns:

> *"Couldn't generate a fit card — outfit description was empty. Make sure suggest_outfit ran successfully before calling this tool."*

**Tested by running:**
```bash
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
# Output: error message string — no exception
```

---

## Spec Reflection

**One way the spec helped:** Writing the agent diagram in `planning.md` before touching `agent.py` made the conditional branch logic very clear. The diagram forced me to decide exactly what "no results" means (early return, not empty string passed forward) before I wrote a single line of the loop — which meant there was no ambiguity when implementing it.

**One way implementation diverged from the spec:** The original spec described using the LLM to parse the query (extract description, size, max_price from natural language). In practice, regex parsing was faster, cheaper, and more predictable for the structured fields (price patterns, size abbreviations). The LLM was kept for the open-ended tasks (outfit suggestion, caption generation) where variability is a feature, not a problem. The `_parse_query()` function documents this choice with inline comments.

---

## AI Tool Usage

**Instance 1 — `search_listings` implementation:**
I gave Claude the Tool 1 spec block from `planning.md` (inputs with types, return value description, failure mode) and the listings schema fields. I asked it to implement keyword scoring using field concatenation. Before using the output, I checked that: (1) it filtered by all three parameters, (2) it handled the empty-results case with `[]` and not an exception, and (3) it dropped zero-score items. I overrode the scoring function — the original used `sum(kw in text for kw in keywords)` without stripping punctuation, which caused "tee." to not match "tee". I changed it to split on whitespace and check substring inclusion across concatenated fields.

**Instance 2 — `suggest_outfit` and `create_fit_card` prompts:**
I gave Claude the Tool 2 and Tool 3 spec blocks plus the caption style rules ("casual, not a product description, mention price and platform once"). The generated prompts were functional but too formal — phrases like "Please provide outfit recommendations" and "The following outfit has been curated." I rewrote the prompt framing to match the "stylish friend" voice described in the spec: *"Be specific about silhouettes, vibe, and how to wear it. Keep it casual and friendly, like advice from a stylish friend who knows their closet."* The fit card prompt also needed the explicit rule "do not use hashtags" added — the first version consistently generated 5–6 hashtags.

---

## Running Tests

```bash
pytest tests/ -v
```

Tests use `unittest.mock` to patch the Groq client — no API calls are made during testing. All failure modes (empty results, empty wardrobe, empty outfit, LLM exceptions) are tested to confirm they return strings rather than raising exceptions.