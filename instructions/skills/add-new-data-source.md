# Skill: Add a new data source

Use this skill when adding any new table that the chatbot should be able to query.

## Checklist

### Step 1 — Design
- [ ] Define the table schema following the pattern in `instructions/domain/data-schema.md`
- [ ] Decide: insert-only or upsertable?
- [ ] Decide: does it need citation? What is the citation label format?
- [ ] Decide: vector search or SQL retrieval?

### Step 2 — Migration
- [ ] Create `scripts/migrations/NNN_create_{table}.sql`
- [ ] Add `IF NOT EXISTS` to all CREATE statements
- [ ] Add insert-only trigger if applicable
- [ ] Add indexes for all FK columns and WHERE columns
- [ ] Run: `python scripts/migrations/run_migrations.py`

### Step 3 — Ingestion job
- [ ] Create `scripts/ingest_{source}.py` following the pattern in existing ingest scripts
- [ ] Insert-only with idempotency check
- [ ] Batch processing — never load all rows into memory
- [ ] structlog logging following CLAUDE.md conventions
- [ ] Add as `--only` phase in `update_all_data.py` if applicable

### Step 4 — Tool definition
- [ ] Add tool to `GOLDMINE_TOOLS` in `backend/app/mode2/tools.py`
- [ ] Tool description must encode routing rules: what queries should use this tool, what should not
- [ ] Add handler in `execute_tool()` routing to the correct `_query_*` function in `retrieval.py`
- [ ] Add `_query_{source}()` function to `retrieval.py` following existing patterns

### Step 5 — Classifier update (if alt data)
- [ ] Add keyword mappings to `ALT_DATA_KEYWORD_MAP` in `classifier.py`
- [ ] Add data_type to alt_data tool enum in `tools.py`

### Step 6 — Documentation (mandatory)
- [ ] Add table to `instructions/domain/data-schema.md`
- [ ] Add to data source access map in `instructions/domain/chatbot.md`
- [ ] If alt data: add keyword mapping table entry in `chatbot.md`

### Step 7 — Tests
- [ ] Update `test_all_tools_present` in `tests_mode2/test_retrieval.py` with the new tool name
- [ ] Run: `cd backend && source .venv/bin/activate && pytest`
- [ ] Run: `python scripts/run_docs_sync.py` — should exit 0
- [ ] Fix all failures before finishing
