import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { EmailSchedule } from "../types/entities";
import { Layout } from "../components/Layout";
import { formatSchedule } from "../components/SchedulesList";
import * as schedulesApi from "../config/schedulesApi";
import "../styles/alerts.css";

export function AlertsPage() {
  const [schedules, setSchedules] = useState<EmailSchedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [sendingId, setSendingId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    schedulesApi
      .listSchedules()
      .then(setSchedules)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

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
    <Layout>
      <div className="alerts-page">
        <div className="alerts-page__header">
          <h2>Alerts</h2>
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
          <div className="alerts-page__loading">
            <div className="spinner" />
          </div>
        )}

        {!loading && schedules.length === 0 && (
          <div className="alerts-page__empty">No alerts configured yet.</div>
        )}

        {!loading && schedules.length > 0 && (
          <div className="alerts-page__list">
            {schedules.map((s) => (
              <div key={s.schedule_id} className="alerts-page__card">
                <div className="alerts-page__card-name">{s.name}</div>
                <div className="alerts-page__card-entity">
                  <Link to={`/entity/${s.entity_type}/${s.entity_id}`}>
                    {s.entity_type}/{s.entity_id}
                  </Link>
                </div>
                <div className="alerts-page__card-recipients">
                  {s.recipients.join(", ")}
                </div>
                <div className="alerts-page__card-schedule">
                  {formatSchedule(s.days_of_week, s.time_of_day)}
                </div>
                <div className="alerts-page__card-status">
                  <span
                    className={`schedules-list__item-status schedules-list__item-status--${s.status}`}
                  >
                    {s.status}
                  </span>
                </div>
                <div className="alerts-page__card-next-run">
                  Next: {formatDate(s.next_run_at)}
                </div>
                <div className="alerts-page__card-actions">
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
    </Layout>
  );
}
