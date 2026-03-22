# Skill: Add a new alt data type

Use this skill when a new alternative data vendor or data type is being added to `alt_data`.

## Checklist

### Step 1 — Design
- [ ] Confirm the `data_type` value (snake_case)
- [ ] Confirm `date_frequency`: daily / weekly / monthly / quarterly
- [ ] Confirm `unit` and whether `growth` is pre-calculated by vendor or must be calculated on ingest

### Step 2 — Ingestion job
- [ ] Create `scripts/ingest_alt_{data_type}.py` or add a new phase to existing alt data ingest script
- [ ] Always filter by `data_type` on all queries — never query `alt_data` without a type filter
- [ ] Pre-calculate `growth` column on ingest

### Step 3 — Keyword mapping (both places — never just one)
- [ ] Add all natural language synonyms to `ALT_DATA_KEYWORD_MAP` in `backend/app/mode2/classifier.py`
- [ ] Add the same synonyms to the `get_alt_data` tool description in `backend/app/mode2/tools.py`
- [ ] Add `data_type` to the `get_alt_data` tool's `data_type` enum in `tools.py`

### Step 4 — Classifier prompt
- [ ] Add the keyword → data_type mapping to the "Alt data keyword mapping" section in the `CLASSIFIER_SYSTEM_PROMPT` in `backend/app/mode2/classifier.py`

### Step 5 — Documentation (mandatory)
- [ ] Add keyword → data_type mapping to the alt data keyword mapping table in `instructions/domain/chatbot.md`
- [ ] Add source vendor and coverage notes to the `alt_data` table section in `instructions/domain/data-schema.md`

### Step 6 — Tests
- [ ] Run: `cd backend && source .venv/bin/activate && pytest`
- [ ] Run: `python scripts/run_docs_sync.py` — CHECK 3 should find no mismatches
- [ ] Fix all failures before finishing
