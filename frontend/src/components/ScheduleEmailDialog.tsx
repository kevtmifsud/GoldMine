import { useState } from "react";
import * as schedulesApi from "../config/schedulesApi";
import type { EmailSchedule, WidgetConfig, WidgetOverrideRef, WidgetStateOverride } from "../types/entities";
import "../styles/schedules.css";

interface ScheduleEmailDialogProps {
  entityType?: string;
  entityId?: string;
  widgets?: WidgetConfig[];
  currentOverrides?: WidgetStateOverride[];
  schedule?: EmailSchedule;
  onSave: () => void;
  onCancel: () => void;
}

/** EST is UTC-5. We display EST hours but store UTC. */
const EST_OFFSET = 5;

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, estHour) => {
  const utcHour = (estHour + EST_OFFSET) % 24;
  const value = `${String(utcHour).padStart(2, "0")}:00`;
  const hour12 = estHour === 0 ? 12 : estHour > 12 ? estHour - 12 : estHour;
  const ampm = estHour < 12 ? "AM" : "PM";
  const label = `${hour12}:00 ${ampm}`;
  return { value, label };
});

/** Convert a stored UTC HH:MM back to the matching HOUR_OPTIONS value. */
function utcToEstOptionValue(utcTime: string): string {
  // The option values ARE utc hours already — just find the match
  const match = HOUR_OPTIONS.find((o) => o.value === utcTime);
  return match ? match.value : HOUR_OPTIONS[0].value;
}

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

export function ScheduleEmailDialog({
  entityType = "",
  entityId = "",
  widgets = [],
  currentOverrides,
  schedule,
  onSave,
  onCancel,
}: ScheduleEmailDialogProps) {
  const isEdit = !!schedule;

  const [name, setName] = useState(schedule?.name ?? "");
  const [recipients, setRecipients] = useState(
    schedule ? schedule.recipients.join(", ") : ""
  );
  const [timeOfDay, setTimeOfDay] = useState(
    utcToEstOptionValue(schedule?.time_of_day ?? "14:00")
  );
  const [recurrenceType, setRecurrenceType] = useState<"daily" | "weekly" | "monthly">(
    (schedule?.recurrence_type as "daily" | "weekly" | "monthly") ?? "weekly"
  );
  const [selectedDays, setSelectedDays] = useState<Set<number>>(
    schedule ? new Set(schedule.days_of_week) : new Set([0, 1, 2, 3, 4])
  );
  const [dayOfMonth, setDayOfMonth] = useState<number>(
    schedule?.day_of_month ?? 1
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleToggleDay = (day: number) => {
    setSelectedDays((prev) => {
      const next = new Set(prev);
      if (next.has(day)) {
        if (next.size === 1) return prev; // keep at least one
        next.delete(day);
      } else {
        next.add(day);
      }
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) return;

    const recipientList = recipients
      .split(",")
      .map((r) => r.trim())
      .filter((r) => r.length > 0);

    if (recipientList.length === 0) {
      setError("Please enter at least one recipient email.");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      if (isEdit) {
        await schedulesApi.updateSchedule(schedule.schedule_id, {
          name: trimmedName,
          recipients: recipientList,
          recurrence_type: recurrenceType,
          time_of_day: timeOfDay,
          days_of_week: recurrenceType === "monthly" ? [0, 1, 2, 3, 4, 5, 6] : Array.from(selectedDays).sort(),
          day_of_month: recurrenceType === "monthly" ? dayOfMonth : null,
        });
      } else {
        // Burst all widgets from the current view using live state
        const widgetOverrides: WidgetOverrideRef[] = widgets.map((w) => {
          const live = currentOverrides?.find((o) => o.widget_id === w.widget_id);
          return {
            widget_id: w.widget_id,
            server_filters: live?.server_filters ?? w.initial_filters,
            sort_by: live?.sort_by ?? w.initial_sort_by,
            sort_order: live?.sort_order ?? w.initial_sort_order,
            visible_columns: live?.visible_columns ?? null,
            page_size: live?.page_size ?? w.default_page_size,
          };
        });

        await schedulesApi.createSchedule({
          name: trimmedName,
          entity_type: entityType,
          entity_id: entityId,
          widget_ids: null,
          recipients: recipientList,
          recurrence_type: recurrenceType,
          time_of_day: timeOfDay,
          days_of_week: recurrenceType === "monthly" ? [0, 1, 2, 3, 4, 5, 6] : Array.from(selectedDays).sort(),
          day_of_month: recurrenceType === "monthly" ? dayOfMonth : null,
          widget_overrides: widgetOverrides,
        });
      }
      onSave();
    } catch {
      setError(
        isEdit
          ? "Failed to update schedule. Please try again."
          : "Failed to create schedule. Please try again."
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="schedule-dialog__overlay" onClick={onCancel}>
      <div className="schedule-dialog" onClick={(e) => e.stopPropagation()}>
        <h3 className="schedule-dialog__title">
          {isEdit ? "Edit Alert" : "Create Alert"}
        </h3>
        <form onSubmit={handleSubmit}>
          <div className="schedule-dialog__field">
            <label htmlFor="schedule-name">Name</label>
            <input
              id="schedule-name"
              type="text"
              className="schedule-dialog__input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Daily AAPL Summary"
              autoFocus
            />
          </div>

          <div className="schedule-dialog__field">
            <label htmlFor="schedule-recipients">Recipients</label>
            <input
              id="schedule-recipients"
              type="text"
              className="schedule-dialog__input"
              value={recipients}
              onChange={(e) => setRecipients(e.target.value)}
              placeholder="email1@example.com, email2@example.com"
            />
          </div>

          <div className="schedule-dialog__field">
            <label htmlFor="schedule-time">Time of Day (EST)</label>
            <select
              id="schedule-time"
              className="schedule-dialog__select"
              value={timeOfDay}
              onChange={(e) => setTimeOfDay(e.target.value)}
            >
              {HOUR_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div className="schedule-dialog__field">
            <label>Recurrence</label>
            <div className="schedule-dialog__radio-group">
              <label className="schedule-dialog__radio">
                <input
                  type="radio"
                  name="recurrence"
                  checked={recurrenceType === "daily"}
                  onChange={() => setRecurrenceType("daily")}
                />
                Daily
              </label>
              <label className="schedule-dialog__radio">
                <input
                  type="radio"
                  name="recurrence"
                  checked={recurrenceType === "weekly"}
                  onChange={() => setRecurrenceType("weekly")}
                />
                Weekly
              </label>
              <label className="schedule-dialog__radio">
                <input
                  type="radio"
                  name="recurrence"
                  checked={recurrenceType === "monthly"}
                  onChange={() => setRecurrenceType("monthly")}
                />
                Monthly
              </label>
            </div>
          </div>

          {recurrenceType !== "monthly" && (
            <div className="schedule-dialog__field">
              <label>Days of Week</label>
              <div className="schedule-dialog__day-picker">
                {DAY_LABELS.map((label, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className={`schedule-dialog__day-btn${selectedDays.has(idx) ? " schedule-dialog__day-btn--active" : ""}`}
                    onClick={() => handleToggleDay(idx)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {recurrenceType === "monthly" && (
            <div className="schedule-dialog__field">
              <label htmlFor="schedule-dom">Day of Month</label>
              <input
                id="schedule-dom"
                type="number"
                className="schedule-dialog__input"
                min={1}
                max={28}
                value={dayOfMonth}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10);
                  if (v >= 1 && v <= 28) setDayOfMonth(v);
                }}
              />
            </div>
          )}

          {error && <div className="schedule-dialog__error">{error}</div>}

          <div className="schedule-dialog__actions">
            <button
              type="button"
              className="schedule-dialog__btn schedule-dialog__btn--cancel"
              onClick={onCancel}
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="schedule-dialog__btn schedule-dialog__btn--save"
              disabled={saving || !name.trim()}
            >
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
