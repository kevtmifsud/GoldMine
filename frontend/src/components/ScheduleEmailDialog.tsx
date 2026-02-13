import { useState } from "react";
import * as schedulesApi from "../config/schedulesApi";
import type { WidgetConfig, WidgetOverrideRef } from "../types/entities";
import "../styles/schedules.css";

interface ScheduleEmailDialogProps {
  entityType: string;
  entityId: string;
  widgets: WidgetConfig[];
  preSelectedWidgetId: string | null;
  onSave: () => void;
  onCancel: () => void;
}

export function ScheduleEmailDialog({
  entityType,
  entityId,
  widgets,
  preSelectedWidgetId,
  onSave,
  onCancel,
}: ScheduleEmailDialogProps) {
  const [name, setName] = useState("");
  const [recipients, setRecipients] = useState("");
  const [recurrence, setRecurrence] = useState("daily");
  const [scope, setScope] = useState<"all" | "selected">(
    preSelectedWidgetId ? "selected" : "all"
  );
  const [selectedWidgets, setSelectedWidgets] = useState<Set<string>>(
    preSelectedWidgetId ? new Set([preSelectedWidgetId]) : new Set()
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleToggleWidget = (widgetId: string) => {
    setSelectedWidgets((prev) => {
      const next = new Set(prev);
      if (next.has(widgetId)) {
        next.delete(widgetId);
      } else {
        next.add(widgetId);
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

    const widgetIds =
      scope === "selected" ? Array.from(selectedWidgets) : null;

    if (scope === "selected" && widgetIds && widgetIds.length === 0) {
      setError("Please select at least one widget.");
      return;
    }

    const widgetOverrides: WidgetOverrideRef[] = widgets
      .filter((w) => widgetIds === null || widgetIds.includes(w.widget_id))
      .map((w) => ({
        widget_id: w.widget_id,
        server_filters: w.initial_filters,
        sort_by: w.initial_sort_by,
        sort_order: w.initial_sort_order,
        visible_columns: null,
        page_size: w.default_page_size,
      }));

    setSaving(true);
    setError(null);

    try {
      await schedulesApi.createSchedule({
        name: trimmedName,
        entity_type: entityType,
        entity_id: entityId,
        widget_ids: widgetIds,
        recipients: recipientList,
        recurrence,
        widget_overrides: widgetOverrides,
      });
      onSave();
    } catch {
      setError("Failed to create schedule. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="schedule-dialog__overlay" onClick={onCancel}>
      <div className="schedule-dialog" onClick={(e) => e.stopPropagation()}>
        <h3 className="schedule-dialog__title">Schedule Email</h3>
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
            <label htmlFor="schedule-recurrence">Recurrence</label>
            <select
              id="schedule-recurrence"
              className="schedule-dialog__select"
              value={recurrence}
              onChange={(e) => setRecurrence(e.target.value)}
            >
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </div>

          <div className="schedule-dialog__field">
            <label>Scope</label>
            <div className="schedule-dialog__radio-group">
              <label className="schedule-dialog__radio">
                <input
                  type="radio"
                  name="scope"
                  checked={scope === "all"}
                  onChange={() => setScope("all")}
                />
                Entire Page
              </label>
              <label className="schedule-dialog__radio">
                <input
                  type="radio"
                  name="scope"
                  checked={scope === "selected"}
                  onChange={() => setScope("selected")}
                />
                Selected Widgets
              </label>
            </div>
          </div>

          {scope === "selected" && (
            <div className="schedule-dialog__field">
              <div className="schedule-dialog__checkbox-group">
                {widgets.map((w) => (
                  <label key={w.widget_id} className="schedule-dialog__checkbox">
                    <input
                      type="checkbox"
                      checked={selectedWidgets.has(w.widget_id)}
                      onChange={() => handleToggleWidget(w.widget_id)}
                    />
                    {w.title}
                  </label>
                ))}
              </div>
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
