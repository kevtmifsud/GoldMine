# Skill: Add a new workflow

Use this skill when adding any new repeatable structured output workflow.

## Checklist

### Step 1 — Design
- [ ] Write the workflow spec in `instructions/domain/workflows.md` following the template at the bottom of that file
- [ ] Define: required inputs, output sections, output table schema
- [ ] Set status: DESIGNED

### Step 2 — Output table migration
- [ ] Create `scripts/migrations/NNN_create_workflow_outputs_{name}.sql`
- [ ] Include all JSONB section columns
- [ ] Include `workflow_run_id` FK, `ticker`, `generated_at`, `generated_by`, `citations` JSONB
- [ ] Run migrations: `python scripts/migrations/run_migrations.py`

### Step 3 — Seed workflow registry
- [ ] Add entry to `scripts/seed_workflow_registry.py`
- [ ] Run: `python scripts/seed_workflow_registry.py`

### Step 4 — Implementation
- [ ] Create `backend/app/workflows/{name}.py` (or `backend/app/workflows/{category}/{name}.py`)
- [ ] Inherit from `WorkflowBase`
- [ ] Set `workflow_name` class attribute
- [ ] Implement `execute()` and `get_registry_entry()`
- [ ] Add the module path to `_WORKFLOW_MODULES` in `backend/app/workflows/registry.py`
- [ ] Use `asyncio.gather` for parallel data pulls
- [ ] Call `_query_*` functions directly from `retrieval.py` — never re-implement database queries inline
- [ ] Write `citations` JSONB for every data point used
- [ ] Handle missing data gracefully — never fail silently, surface gaps in output

### Step 5 — Scheduling (if applicable)
- [ ] Add schedule rule to workflow_registry entry
- [ ] Add scheduler logic to `scripts/run_scheduled_workflows.py`

### Step 6 — Documentation (mandatory)
- [ ] Update status to IMPLEMENTED [date] in `instructions/domain/workflows.md`
- [ ] Add output table to `instructions/domain/data-schema.md`
- [ ] Add workflow name to `run_workflow` tool description in `tools.py` (inputs example)

### Step 7 — Tests
- [ ] Run: `cd backend && source .venv/bin/activate && pytest`
- [ ] Run: `python scripts/run_docs_sync.py` — should exit 0
- [ ] Fix all failures before finishing
