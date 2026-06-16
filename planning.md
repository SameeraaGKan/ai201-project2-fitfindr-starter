# FitFindr — planning.md

> Written before implementation. Updated before stretch features.

---

## Tools

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for secondhand items matching the user's natural language description, filtering by size and price ceiling when provided. Returns a relevance-ranked list of matching listing dicts.

**Input parameters:**
- `description` (str): Keywords describing the item the user wants (e.g. "vintage graphic tee"). Used for keyword scoring against title, description, category, style_tags, colors, and brand.
- `size` (str | None): Size string to filter on (e.g. "M", "W30", "US 8"). Case-insensitive substring match against the listing's size field. None skips size filtering.
- `max_price` (float | None): Maximum price inclusive. None skips price filtering.

**What it returns:**
A list of listing dicts sorted by relevance score (highest first). Each dict contains: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str or None), `platform`. Returns `[]` if nothing matches — never raises an exception.

**What happens if it fails or returns nothing:**
The agent checks `if not results` immediately after the call. If empty, it sets `session["error"]` to a user-friendly message naming the failed filters and suggesting what to try differently (broader keywords, remove size/price filter). The agent returns early — `suggest_outfit` and `create_fit_card` are never called with empty input.

---

### Tool 2: suggest_outfit

**What it does:**
Calls the Groq LLM to suggest 1–2 complete outfit combinations using the thrifted item and pieces from the user's existing wardrobe. If the wardrobe is empty, it generates general styling advice for the item instead.

**Input parameters:**
- `new_item` (dict): A full listing dict (the top result from `search_listings`). Used to extract title, description, style_tags, colors, price, and platform for the prompt.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe item dicts. Each item has: `id`, `name`, `category`, `colors` (list), `style_tags` (list), `notes` (str or None). The `items` list may be empty.

**What it returns:**
A non-empty string with outfit suggestions. If the wardrobe is empty, it's general styling advice (what silhouettes, colors, and shoes work with this piece). If the wardrobe has items, it names specific wardrobe pieces and describes complete looks.

**What happens if it fails or returns nothing:**
If the LLM call raises an exception, the tool catches it and returns a descriptive error string (not an empty string, not a raised exception). The agent checks for an error prefix or empty string before proceeding to `create_fit_card`.

---

### Tool 3: create_fit_card

**What it does:**
Calls the Groq LLM to generate a 2–4 sentence Instagram/TikTok-style OOTD caption for the thrifted piece and outfit. Uses a high temperature (1.0) to ensure varied output across calls.

**Input parameters:**
- `outfit` (str): The outfit suggestion string from `suggest_outfit`. Must be non-empty.
- `new_item` (dict): The listing dict for the thrifted item, used for title, price, platform, colors, and style_tags.

**What it returns:**
A 2–4 sentence caption string that sounds like a real person posting their OOTD — casual, specific, mentioning the item name, price, and platform once each. If `outfit` is empty or whitespace-only, returns a descriptive error message string instead of raising.

**What happens if it fails or returns nothing:**
Guards against empty `outfit` before calling the LLM. If the LLM call fails, catches the exception and returns a user-friendly error string noting that the outfit suggestion was saved and to try again.

---

## Planning Loop

The agent uses a sequential conditional loop — it does not call all three tools unconditionally. Here is the exact branch logic:

```
Step 1: Parse query → extract (description, size, max_price) via regex
        Store in session["parsed"]

Step 2: Call search_listings(description, size, max_price)
        Store results in session["search_results"]

        IF results == []:
            session["error"] = "No listings found for '<description>'
                                with filters: <size>, <max_price>.
                                Try removing size/price filter or using different keywords."
            RETURN session   ← early exit; suggest_outfit never called

        ELSE:
            session["selected_item"] = results[0]   ← top relevance result

Step 3: Call suggest_outfit(session["selected_item"], session["wardrobe"])
        Store in session["outfit_suggestion"]

        IF outfit is empty OR starts with "Error:":
            session["error"] = "Found a great listing but couldn't generate
                                outfit suggestions. Item: <title>. Try again."
            RETURN session   ← early exit; create_fit_card never called

Step 4: Call create_fit_card(session["outfit_suggestion"], session["selected_item"])
        Store in session["fit_card"]

Step 5: RETURN session   ← success path; all three fields populated
```

The loop responds to what was returned at each step rather than running all tools in a fixed sequence regardless of context.

---

## State Management

All state lives in a single `session` dict initialized by `_new_session()` at the start of each `run_agent()` call. The dict is the single source of truth — no globals, no re-prompting the user.

| Key | Set in step | Passed to |
|-----|-------------|-----------|
| `query` | Step 1 (init) | Used in error messages |
| `parsed` | Step 1 | Step 2 (`search_listings` args) |
| `search_results` | Step 2 | Step 3 (to pick `selected_item`) |
| `selected_item` | Step 3 | Step 4 (`suggest_outfit`) and Step 5 (`create_fit_card`) |
| `wardrobe` | Step 1 (init) | Step 4 (`suggest_outfit`) |
| `outfit_suggestion` | Step 4 | Step 5 (`create_fit_card`) |
| `fit_card` | Step 5 | Returned to UI |
| `error` | Any step on failure | Returned to UI; stops further tool calls |

`app.py` reads `session["error"]`, `session["selected_item"]`, `session["outfit_suggestion"]`, and `session["fit_card"]` to populate the three output panels.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No results match query + filters | Sets `session["error"]` with message naming the failed filters and suggesting specific adjustments (remove size filter, try different keywords). Returns session early — `suggest_outfit` is never called with empty input. |
| `suggest_outfit` | Wardrobe is empty | Calls LLM with a general styling prompt instead of a wardrobe-specific one. Returns general advice string — no crash, no empty string. |
| `suggest_outfit` | LLM call raises exception | Catches exception, returns descriptive error string starting with "Couldn't generate outfit suggestions..." |
| `create_fit_card` | `outfit` arg is empty/whitespace | Guards at the top of the function before the LLM call. Returns error string: "Couldn't generate a fit card — outfit description was empty." |
| `create_fit_card` | LLM call raises exception | Catches exception, returns error string noting the outfit was saved and to try again. |

---

## Architecture

```
User query (natural language)
    │
    ▼
run_agent(query, wardrobe)
    │
    ├─ Step 1: _parse_query(query)
    │       Regex extracts: description, size, max_price
    │       → session["parsed"]
    │
    ├─ Step 2: search_listings(description, size, max_price)
    │       → session["search_results"]
    │       │
    │       ├── results == [] ──► session["error"] = "No listings found..."
    │       │                     RETURN session (early exit) ──────────────────┐
    │       │                                                                   │
    │       └── results found → session["selected_item"] = results[0]          │
    │                                                                           │
    ├─ Step 3: suggest_outfit(selected_item, wardrobe)                          │
    │       │                                                                   │
    │       ├── wardrobe empty → LLM: general styling advice                   │
    │       ├── wardrobe has items → LLM: specific wardrobe combos              │
    │       ├── LLM error → return error string                                 │
    │       │                                                                   │
    │       → session["outfit_suggestion"]                                      │
    │       │                                                                   │
    │       ├── outfit empty/error ─► session["error"] = "Couldn't generate..."│
    │       │                          RETURN session (early exit) ─────────────┤
    │       │                                                                   │
    │       └── outfit ok → proceed                                             │
    │                                                                           │
    ├─ Step 4: create_fit_card(outfit_suggestion, selected_item)                │
    │       │                                                                   │
    │       ├── outfit empty → return error string (no LLM call)               │
    │       ├── LLM error → return error string                                 │
    │       └── success → session["fit_card"] = caption                        │
    │                                                                           │
    └─ Step 5: RETURN session ◄──────────────────────────────────────────────┘
                    │
                    ▼
            app.py → handle_query()
                    │
                    ├── session["error"] set? → panel 1: error msg, panels 2&3: ""
                    └── success? → panel 1: formatted listing
                                   panel 2: outfit_suggestion
                                   panel 3: fit_card
```

---

## AI Tool Plan

### Milestone 3 — Individual tool implementations

**Tool 1 (`search_listings`):**
Used Claude with the Tool 1 spec block (description, inputs with types, return value, failure mode) plus the listings schema fields from `data/listings.json`. Asked it to implement keyword scoring using field concatenation and a dict comprehension. Verified the generated code filtered by all three parameters and handled the empty-results case with `[]` not an exception. Tested with 3 queries: "vintage tee" (expects results), "ballgown size XXS under $5" (expects `[]`), "jacket under $40" (expects price-filtered results).

**Tool 2 (`suggest_outfit`):**
Used Claude with the Tool 2 spec block and the wardrobe schema. Asked it to branch on `wardrobe['items']` being empty and write two distinct prompts — one for general styling, one naming specific wardrobe pieces. Verified the branch existed in the generated code before running it. Tested with `get_example_wardrobe()` and `get_empty_wardrobe()` and confirmed neither raised an exception.

**Tool 3 (`create_fit_card`):**
Used Claude with the Tool 3 spec block and the caption style rules. Asked it to guard against empty outfit before the LLM call and set `temperature=1.0`. Verified the guard clause was at the top of the function. Ran it 3 times on the same input to confirm output varied; confirmed it returned an error string (not an exception) for empty outfit input.

### Milestone 4 — Planning loop and state management

Used Claude with the full Architecture diagram and the Planning Loop + State Management sections. Asked it to implement `run_agent()` following the conditional logic in the diagram exactly. Before running: verified the code branched on `if not results` before calling `suggest_outfit`, verified state was stored in the session dict at each step (not passed as local variables only), and verified no tool was called unconditionally. Tested the no-results branch manually with `python agent.py`.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Parse query:**
`_parse_query()` extracts:
- `description = "I'm looking for a vintage graphic tee. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it"`
- `size = None` (no size mentioned)
- `max_price = 30.0` (extracted from "under $30")

These are stored in `session["parsed"]`.

**Step 2 — Search listings:**
`search_listings("vintage graphic tee ...", size=None, max_price=30.0)` is called.

Filtering step: listings with `price > 30` are dropped. No size filter.

Scoring step: keywords like "vintage", "graphic", "tee" match listings 002, 006, 015, 033 strongly. lst_006 ("Graphic Tee — 2003 Tour Bootleg Style", $24, depop) and lst_033 ("Vintage Band Tee — Faded Grey", $19, depop) score highest.

`session["search_results"]` = [lst_006, lst_033, lst_002, lst_015, ...]
`session["selected_item"]` = lst_006 (top result)

**Step 3 — Suggest outfit:**
`suggest_outfit(lst_006, example_wardrobe)` is called.

Wardrobe has 10 items — not empty, so the LLM receives a prompt naming specific pieces. The prompt includes the tee's details and the wardrobe list.

LLM returns: *"Pair this boxy graphic tee with your baggy dark-wash jeans and chunky white sneakers for a classic 90s streetwear look — tuck the front corner in slightly for shape. Or layer it under your black denim jacket with the dark jeans and black combat boots for a grungier take."*

`session["outfit_suggestion"]` = above string.

**Step 4 — Fit card:**
`create_fit_card(outfit_suggestion, lst_006)` is called.

LLM (temperature=1.0) receives the outfit and item details and generates a caption.

Returns: *"thrifted this faded 2003 bootleg tee off depop for $24 and honestly my baggy jeans have never looked better 🖤 tucked the front corner in and suddenly it's a whole outfit. full look on my page."*

`session["fit_card"]` = above string.

**Final output to user:**
- Panel 1 (listing): "✅ Found 4 matches — showing top result: 📌 Graphic Tee — 2003 Tour Bootleg Style | 💰 $24.00 | depop | Size L | Condition: Good"
- Panel 2 (outfit): The 2-outfit suggestion from Step 3
- Panel 3 (fit card): The caption from Step 4

**Error path (what if no results):**
If the user had searched "designer ballgown size XXS under $5", `search_listings` returns `[]`. The agent sets `session["error"] = "No listings found for 'designer ballgown' with filters: size XXS, under $5. Try broadening your search..."` and returns immediately. `suggest_outfit` and `create_fit_card` are never called. Panel 1 shows the error message; panels 2 and 3 are empty.