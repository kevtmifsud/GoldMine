# Skill: Add a new sheet to the financial model template

Use this skill when the canonical model template in `instructions/domain/models.md` needs a new sheet.

## Checklist

### Step 1 — Design
- [ ] Add the sheet spec to `instructions/domain/models.md` with all required rows, naming conventions, and period structure
- [ ] Confirm sheet name (CAPS, no spaces — the model processing job finds sheets by exact name)

### Step 2 — Model processing job
- [ ] Add parser for new sheet in `scripts/model_processing_job.py`
- [ ] Follow existing sheet parsing pattern exactly
- [ ] Map to `model_outputs` rows: `sheet`, `metric`, `period`, `scenario`, `value`, `unit`
- [ ] Log unmapped metric names as warnings

### Step 3 — Backfill
- [ ] Run `scripts/backfill_portfolio_tables.py` if the new sheet affects historical data
- [ ] Or re-run `model_processing_job` for affected tickers

### Step 4 — Documentation (mandatory)
- [ ] Sheet is already added to `models.md` in Step 1
- [ ] If new metrics flow to `internal_estimates`, document them in `data-schema.md`

### Step 5 — Tests
- [ ] Run: `cd backend && source .venv/bin/activate && pytest`
- [ ] Run: `python scripts/run_docs_sync.py` — should exit 0
- [ ] Fix all failures before finishing
