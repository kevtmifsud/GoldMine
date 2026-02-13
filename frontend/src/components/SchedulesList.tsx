import { useCallback, useEffect, useState } from "react";
import * as schedulesApi from "../config/schedulesApi";
import type { EmailSchedule } from "../types/entities";
import "../styles/schedules.css";

interface SchedulesListProps {
  entityType: string;
  entityId: string;
  refreshKey?: number;
}

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function utcHourToEst(utcHour: number): number {
  return (utcHour - 5 + 24) % 24;
}

export function formatSchedule(
  days_of_week: number[],
  time_of_day: string,
  recurrence_type?: string,
  day_of_month?: number | null,
): string {
  const [hourStr, minuteStr] = time_of_day.split(":");
  const utcHour = parseInt(hourStr, 10);
  const estHour = utcHourToEst(utcHour);
  const hour12 = estHour === 0 ? 12 : estHour > 12 ? estHour - 12 : estHour;
  const ampm = estHour < 12 ? "AM" : "PM";
  const timeLabel = `${hour12}:${minuteStr} ${ampm} EST`;

  if (recurrence_type === "monthly" && day_of_month != null) {
    return `Monthly on the ${day_of_month}${ordinalSuffix(day_of_month)} @ ${timeLabel}`;
  }

  if (recurrence_type === "daily") {
    return `Daily @ ${timeLabel}`;
  }

  const dayNames = days_of_week
    .slice()
    .sort()
    .map((d) => DAY_LABELS[d] ?? `Day${d}`);

  return `${dayNames.join(", ")} @ ${timeLabel}`;
}

function ordinalSuffix(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "st";
  if (mod10 === 2 && mod100 !== 12) return "nd";
  if (mod10 === 3 && mod100 !== 13) return "rd";
  return "th";
}

export function SchedulesList({
  entityType,
  entityId,
  refreshKey,
}: SchedulesListProps) {
  const [schedules, setSchedules] = useState<EmailSchedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [sendingId, setSendingId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const fetchSchedules = useCallback(async () => {
    setLoading(true);
    try {
      const data = await schedulesApi.listSchedules(entityType, entityId);
      setSchedules(data);
    } catch {
      // Silently fail — empty list is fine
    } finally {
      setLoading(false);
    }
  }, [entityType, entityId]);

  useEffect(() => {
    fetchSchedules();
  }, [fetchSchedules, refreshKey]);

  const handleSendNow = async (scheduleId: string) => {
    setSendingId(scheduleId);
    setFeedback(null);
    try {
      const log = await schedulesApi.sendNow(scheduleId);
      setFeedback(
        log.status === "sent"
          ? "Email sent successfully!"
          : `Send failed: ${log.error || "Unknown error"}`
      );
    } catch {
      setFeedback("Failed to send email.");
    } finally {
      setSendingId(null);
      setTimeout(() => setFeedback(null), 3000);
    }
  };

  const handleDelete = async (scheduleId: string) => {
    try {
      await schedulesApi.deleteSchedule(scheduleId);
      setSchedules((prev) =>
        prev.filter((s) => s.schedule_id !== scheduleId)
      );
    } catch {
      setFeedback("Failed to delete schedule.");
      setTimeout(() => setFeedback(null), 3000);
    }
  };

  const formatDate = (iso: string) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  return (
    <div className="schedules-list">
      <div className="schedules-list__header">
        <h3 className="schedules-list__title">Email Schedules</h3>
      </div>

      {feedback && (
        <div
          style={{
            fontSize: "0.85rem",
            marginBottom: "0.75rem",
            color: feedback.includes("success")
              ? "var(--color-success)"
              : "var(--color-error)",
          }}
        >
          {feedback}
        </div>
      )}

      {loading && (
        <div style={{ color: "var(--color-text-secondary)", padding: "1rem 0" }}>
          Loading...
        </div>
      )}

      {!loading && schedules.length === 0 && (
        <div className="schedules-list__empty">No email schedules yet.</div>
      )}

      {!loading && schedules.length > 0 && (
        <div className="schedules-list__list">
          {schedules.map((s) => (
            <div key={s.schedule_id} className="schedules-list__item">
              <div className="schedules-list__item-info">
                <div className="schedules-list__item-name">{s.name}</div>
                <div className="schedules-list__item-meta">
                  <span className="schedules-list__item-recurrence">
                    {formatSchedule(s.days_of_week, s.time_of_day, s.recurrence_type, s.day_of_month)}
                  </span>
                  <span className="schedules-list__item-next-run">
                    Next: {formatDate(s.next_run_at)}
                  </span>
                  <span
                    className={`schedules-list__item-status schedules-list__item-status--${s.status}`}
                  >
                    {s.status}
                  </span>
                </div>
              </div>
              <div className="schedules-list__item-actions">
                <button
                  className="schedules-list__item-btn"
                  onClick={() => handleSendNow(s.schedule_id)}
                  disabled={sendingId === s.schedule_id}
                >
                  {sendingId === s.schedule_id ? "Sending..." : "Send Now"}
                </button>
                <button
                  className="schedules-list__item-btn schedules-list__item-btn--danger"
                  onClick={() => handleDelete(s.schedule_id)}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
