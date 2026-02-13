# GoldMine Phase 5 — Email & Scheduling System

## Context

Phase 4 delivered document ingestion, keyword search, and LLM-powered research queries. Phase 5 adds an email scheduling system enabling users to schedule automated email deliverables for individual widgets or entire entity pages. Emails are sent on a configurable day-of-week and time-of-day basis (e.g. Mon/Wed/Fri at 9:00 AM UTC) and reflect the current state of widgets including applied filters and layout. On creation, a burst send is performed immediately. A top-level Alerts page (`/alerts`) lists all of the current user's schedules across entities.

**User decisions:**
- Email delivery: Console/file mock — renders HTML emails and logs to JSON file + console. No real SMTP. Swappable later.
- Scheduler: In-process background asyncio task checking for due schedules every 60 seconds. No external dependencies.
- Email content: HTML tables rendered server-side from widget data at send time using stored filters/overrides.

**Key patterns to follow (established in Phases 0-4):**
- Backend: factory+provider singletons, Pydantic models, `from __future__ import annotations`, `request.state.user`
- Frontend: functional components with hooks, BEM CSS, axios API services in `config/`
- Data: JSON flat files in `data/schedules/`
- Tests: pytest-asyncio, httpx AsyncClient, autouse fixture resets providers

---

## New Files (17)

| File | Purpose |
|------|---------|
| `backend/app/email/__init__.py` | Package init |
| `backend/app/email/models.py` | Pydantic models: EmailSchedule, EmailLog, EmailScheduleCreate, EmailScheduleUpdate |
| `backend/app/email/interfaces.py` | Abstract EmailProvider + ScheduleProvider |
| `backend/app/email/console_provider.py` | Console/file email mock — logs to JSON + stdout |
| `backend/app/email/json_schedule_provider.py` | JSON flat-file schedule persistence |
| `backend/app/email/factory.py` | Singleton factories for email + schedule providers |
| `backend/app/email/renderer.py` | HTML email renderer — fetches widget data, renders styled tables |
| `backend/app/email/scheduler.py` | Background asyncio task — checks due schedules, renders + sends, handles retries |
| `backend/app/api/schedules.py` | REST router: CRUD for schedules, logs, send-now |
| `backend/app/tests/test_schedules.py` | Schedule CRUD API tests |
| `backend/app/tests/test_email_renderer.py` | HTML rendering tests |
| `backend/app/tests/test_scheduler.py` | Due schedule detection + retry logic tests |
| `frontend/src/config/schedulesApi.ts` | Typed API service for schedules |
| `frontend/src/components/ScheduleEmailDialog.tsx` | Modal for creating/editing email schedules |
| `frontend/src/components/SchedulesList.tsx` | Panel showing user's schedules for an entity |
| `frontend/src/styles/schedules.css` | All Phase 5 component styles |
| `data/schedules/.gitkeep` | Placeholder for schedules data directory |

## Modified Files (7)

| File | Change |
|------|--------|
| `backend/app/config/settings.py` | Add `SCHEDULES_DIR`, `SCHEDULER_INTERVAL_SECONDS`, `EMAIL_MAX_ROWS_PER_WIDGET` |
| `backend/app/main.py` | Register `schedules_router`, start scheduler background task on startup |
| `backend/app/tests/conftest.py` | Reset email/schedule providers, temp schedules dir |
| `frontend/src/types/entities.ts` | Add EmailSchedule, EmailLog, EmailScheduleCreate, EmailScheduleUpdate interfaces |
| `frontend/src/pages/EntityPage.tsx` | Add "Schedule Email" button + SchedulesList panel |
| `frontend/src/styles/entity.css` | Spacing for schedules panel |
| `backend/.env.example` | Add new env vars |

---

## Stage 1: Backend Email Models + Interfaces + Providers

**New files:** `backend/app/email/__init__.py`, `models.py`, `interfaces.py`, `console_provider.py`, `json_schedule_provider.py`, `factory.py`

**`models.py`** — Core data models:
- `EmailSchedule(schedule_id, owner, name, entity_type, entity_id, widget_ids: list[str] | None, recipients: list[str], time_of_day: str, days_of_week: list[int], next_run_at: str, last_run_at: str, status: str, widget_overrides: list[WidgetOverrideRef], retry_count: int, created_at, updated_at)` — `widget_ids=None` means full entity page; `time_of_day` is `"HH:MM"` format (default `"09:00"`); `days_of_week` is list of 0–6 (Mon=0, Sun=6, default weekdays `[0,1,2,3,4]`); `status` is one of `"active"`, `"paused"`, `"failed"`
- `WidgetOverrideRef(widget_id, server_filters, sort_by, sort_order, visible_columns, page_size)` — captures the widget state at schedule creation time (reuses same shape as `WidgetStateOverride` from views)
- `EmailLog(log_id, schedule_id, sent_at, status: str, error: str | None, recipients: list[str])` — `status` is `"sent"` or `"failed"`
- `EmailScheduleCreate(name, entity_type, entity_id, widget_ids: list[str] | None, recipients: list[str], time_of_day: str, days_of_week: list[int], widget_overrides: list[WidgetOverrideRef])` — request body for creation
- `EmailScheduleUpdate(name: str | None, recipients: list[str] | None, time_of_day: str | None, days_of_week: list[int] | None, status: str | None, widget_overrides: list[WidgetOverrideRef] | None)` — partial update

**`interfaces.py`** — Two abstract classes:
- `EmailProvider` with: `send_email(recipients: list[str], subject: str, html_body: str, text_body: str) -> bool`
- `ScheduleProvider` with: `create_schedule()`, `get_schedule()`, `list_schedules()`, `update_schedule()`, `delete_schedule()`, `get_due_schedules()`, `add_log()`, `get_logs()`

**`console_provider.py`** — `ConsoleEmailProvider`:
- `send_email()` logs to console via structlog and appends entry to `{SCHEDULES_DIR}/email_log.json`
- Returns `True` always (mock never fails unless explicitly testing)

**`json_schedule_provider.py`** — `JsonScheduleProvider`:
- Stores schedules in `{SCHEDULES_DIR}/schedules.json`, logs in `{SCHEDULES_DIR}/delivery_log.json`
- `get_due_schedules()`: filters schedules where `status == "active"` and `next_run_at <= now`
- Same read/write pattern as `views/json_provider.py`

**`factory.py`** — Two singleton factories:
- `get_email_provider() -> EmailProvider` — returns ConsoleEmailProvider
- `get_schedule_provider() -> ScheduleProvider` — returns JsonScheduleProvider(settings.SCHEDULES_DIR)

**Modify `backend/app/config/settings.py`:**
```python
SCHEDULES_DIR: str = "../data/schedules"
SCHEDULER_INTERVAL_SECONDS: int = 60
EMAIL_MAX_ROWS_PER_WIDGET: int = 50
```

---

## Stage 2: Email Renderer

**New file:** `backend/app/email/renderer.py`

`render_email(entity_type, entity_id, widget_ids, widget_overrides) -> (subject, html_body, text_body)`:

1. Fetch entity structured data via `get_data_provider().get_record()` — build header section (entity name, key fields)
2. Build entity detail via the same `_build_stock_detail()` / `_build_person_detail()` / `_build_dataset_detail()` helpers used in `api/entities.py` — import them directly
3. For each widget (filtered by `widget_ids` if provided, or all widgets):
   - Apply `widget_overrides` if present (server_filters, sort, visible_columns)
   - Fetch widget data by calling the data provider directly (not via HTTP) using the widget's endpoint pattern to determine the dataset/query
   - Build `FilterParams` from overrides and query the data provider
   - Truncate to `EMAIL_MAX_ROWS_PER_WIDGET` rows
4. Render HTML with inline CSS: entity header card + one HTML `<table>` per widget with column headers and data rows
5. Generate plain text fallback: entity name + tab-separated tables
6. Subject line: `"GoldMine: {entity_display_name} — {schedule_name}"`

---

## Stage 3: Background Scheduler

**New file:** `backend/app/email/scheduler.py`

`start_scheduler(app: FastAPI)` — registers an `on_startup` background task:

```python
async def _scheduler_loop():
    while True:
        await asyncio.sleep(settings.SCHEDULER_INTERVAL_SECONDS)
        await _process_due_schedules()
```

`_process_due_schedules()`:
1. Call `get_schedule_provider().get_due_schedules()` — returns schedules where `next_run_at <= now` and `status == "active"`
2. For each due schedule:
   a. Render email via `render_email()`
   b. Send via `get_email_provider().send_email()`
   c. On success: log as `"sent"`, reset `retry_count` to 0, compute `next_run_at` based on recurrence
   d. On failure: increment `retry_count`, log as `"failed"` with error
      - If `retry_count < 3`: set `next_run_at` to now + 5 minutes (retry)
      - If `retry_count >= 3`: set `status = "failed"`, log final failure
3. All processing in `asyncio.to_thread()` to avoid blocking the event loop

`_compute_next_run(current: datetime, days_of_week: list[int], time_of_day: str) -> str`:
- From `current + 1 day`, walks forward to find the next day whose `weekday()` is in `days_of_week`, sets time to `time_of_day` UTC

---

## Stage 4: Backend Schedules API Router

**New file:** `backend/app/api/schedules.py`

Router prefix: `/api/schedules`, tags: `["schedules"]`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/schedules/` | Create schedule. Body: EmailScheduleCreate. Sets `owner` from `request.state.user`, generates `schedule_id`, computes initial `next_run_at` from `time_of_day`+`days_of_week`, performs a burst send immediately. Returns 201. |
| `GET` | `/api/schedules/` | List user's schedules. Optional `entity_type`, `entity_id` query filters. Returns only schedules owned by current user. |
| `GET` | `/api/schedules/{schedule_id}` | Get single schedule. 404 if not found or not owned by user. |
| `PUT` | `/api/schedules/{schedule_id}` | Update schedule. Owner only. Body: EmailScheduleUpdate. Recomputes `next_run_at` if `time_of_day` or `days_of_week` changed. |
| `DELETE` | `/api/schedules/{schedule_id}` | Delete schedule. Owner only. Returns 204. |
| `GET` | `/api/schedules/{schedule_id}/logs` | Get delivery logs for a schedule. Returns list of EmailLog sorted by sent_at desc. Owner only. |
| `POST` | `/api/schedules/{schedule_id}/send-now` | Trigger immediate send for testing. Renders + sends email, creates log entry. Owner only. |

---

## Stage 5: Backend Tests

- `test_schedules.py` — 13 tests: CRUD, owner-only access, send-now, auth required, burst send on create, next_run respects days_of_week
- `test_email_renderer.py` — 3 tests: stock email rendering, single widget, row truncation
- `test_scheduler.py` — 4 tests: due schedule detection, success processing, retry logic, compute_next_run skips non-matching days

---

## Stage 6-8: Frontend

- TypeScript interfaces added to `entities.ts` (EmailSchedule, EmailLog, etc.)
- `schedulesApi.ts` — 7 typed API functions
- `ScheduleEmailDialog.tsx` — Modal with name, recipients, time-of-day picker, day-of-week checkboxes, scope (entire page / selected widgets)
- `SchedulesList.tsx` — Panel showing schedule cards with formatted days+time (e.g. "Mon, Wed, Fri @ 9:00 AM"), Send Now / Delete buttons
- `AlertsPage.tsx` — Top-level `/alerts` page listing all user schedules across entities with entity links, recipients, schedule info, status, and actions
- `alerts.css` — BEM styles for alerts page
- `schedules.css` — Full BEM styling including day-picker toggle buttons
- `EntityPage.tsx` — "Schedule Email" button + SchedulesList panel below LLM panel
- `Layout.tsx` — "Alerts" nav link added to header
- `App.tsx` — `/alerts` route added

---

## Key Design Decisions

1. **Console/file mock email provider** — No real SMTP needed for demo. Emails rendered to HTML and logged to `email_log.json` + console. The `EmailProvider` interface makes swapping to real SMTP a one-file change.
2. **In-process background scheduler** — A simple `asyncio.create_task` loop that checks for due schedules every 60 seconds. No external dependency (no Celery, no APScheduler). Adequate for demo scale.
3. **Server-side HTML rendering** — Widget data re-fetched at send time using stored overrides, rendered as styled HTML tables with inline CSS. This gives email recipients a faithful snapshot of the widget data.
4. **Data fetched directly, not via HTTP** — The renderer calls `get_data_provider().query()` directly rather than making HTTP requests to widget endpoints. This avoids auth/networking issues in the background task.
5. **Retry policy: 3 retries at 5-minute intervals** — Failed sends increment `retry_count`. After 3 failures, schedule status set to `"failed"`. Users can see this in the UI.
6. **Widget overrides captured at creation time** — When a user creates a schedule, the current widget filter/sort/column state is captured and stored with the schedule. This ensures emails always reflect the intended view.
7. **Granular day-of-week + time-of-day scheduling** — Replaced simple recurrence (daily/weekly/monthly) with explicit day-of-week selection (multi-select, 0=Mon through 6=Sun) and time-of-day in HH:MM format. This enables schedules like "Mon, Wed, Fri at 9:00 AM UTC".
8. **Burst send on creation** — When a schedule is first created, the email is immediately sent (burst). The schedule's `next_run_at` remains at the computed future time. This gives users immediate feedback.
9. **Alerts page** — A top-level `/alerts` route lists all of the current user's schedules across all entities, providing a single view of all configured email alerts with entity links and management actions.
7. **Separate panels, not widgets** — Like Documents/LLM in Phase 4, the Schedules panel lives below the widget grid and doesn't participate in the views/overrides system.
10. **`python-dateutil` for retry arithmetic** — `relativedelta` used for retry interval calculations in the scheduler.
