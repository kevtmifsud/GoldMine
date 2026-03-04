import { useEffect, useState } from "react";
import type { EmailSchedule } from "../types/entities";
import { Layout } from "../components/Layout";
import { ScheduleEmailDialog } from "../components/ScheduleEmailDialog";
import { formatSchedule } from "../components/SchedulesList";
import * as reportsApi from "../config/reportsApi";
import type { ReportDefinition } from "../config/reportsApi";
import * as schedulesApi from "../config/schedulesApi";
import { useAuth } from "../auth/useAuth";
import "../styles/reports.css";

export function ReportsPage() {
  const { user } = useAuth();
  const [reports, setReports] = useState<ReportDefinition[]>([]);
  const [subscriptions, setSubscriptions] = useState<EmailSchedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [sendingId, setSendingId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [subscribingReport, setSubscribingReport] =
    useState<ReportDefinition | null>(null);

  const fetchData = () => {
    Promise.all([
      reportsApi.listReports(),
      schedulesApi.listSchedules("report"),
    ])
      .then(([reportData, scheduleData]) => {
        setReports(reportData);
        setSubscriptions(scheduleData);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData();
  }, []);

  const subscribedReportIds = new Set(
    subscriptions.map((s) => s.entity_id)
  );

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
      setSubscriptions((prev) =>
        prev.filter((s) => s.schedule_id !== scheduleId)
      );
    } catch {
      setFeedback("Failed to delete subscription.");
      setTimeout(() => setFeedback(null), 3000);
    }
  };

  const formatDate = (iso: string) => {
    if (!iso) return "\u2014";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  return (
    <Layout>
      <div className="reports-page">
        <div className="reports-page__header">
          <h2>Reports</h2>
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
          <div className="reports-page__loading">
            <div className="spinner" />
          </div>
        )}

        {!loading && (
          <>
            {/* Available Reports */}
            <h3 className="reports-page__section-title">Available Reports</h3>
            <div className="reports-page__catalog">
              {reports.map((r) => (
                <div key={r.report_id} className="reports-page__report-card">
                  <div className="reports-page__report-badges">
                    <span className="reports-page__badge reports-page__badge--category">
                      {r.category}
                    </span>
                    {subscribedReportIds.has(r.report_id) && (
                      <span className="reports-page__badge reports-page__badge--subscribed">
                        Subscribed
                      </span>
                    )}
                  </div>
                  <div className="reports-page__report-name">{r.name}</div>
                  <div className="reports-page__report-desc">
                    {r.description}
                  </div>
                  <div className="reports-page__report-actions">
                    <button
                      className="reports-page__subscribe-btn"
                      onClick={() => setSubscribingReport(r)}
                    >
                      Subscribe
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* My Subscriptions */}
            <h3 className="reports-page__section-title">My Subscriptions</h3>
            {subscriptions.length === 0 && (
              <div className="reports-page__empty">
                No report subscriptions yet.
              </div>
            )}
            {subscriptions.length > 0 && (
              <div className="reports-page__subs-list">
                {subscriptions.map((s) => (
                  <div key={s.schedule_id} className="reports-page__sub-card">
                    <div className="reports-page__sub-name">{s.name}</div>
                    <div className="reports-page__sub-report">
                      {s.entity_id}
                    </div>
                    <div className="reports-page__sub-recipients">
                      {s.recipients.join(", ")}
                    </div>
                    <div className="reports-page__sub-schedule">
                      {formatSchedule(
                        s.days_of_week,
                        s.time_of_day,
                        s.recurrence_type,
                        s.day_of_month
                      )}
                    </div>
                    <div className="reports-page__sub-status">
                      <span
                        className={`schedules-list__item-status schedules-list__item-status--${s.status}`}
                      >
                        {s.status}
                      </span>
                    </div>
                    <div className="reports-page__sub-next-run">
                      Next: {formatDate(s.next_run_at)}
                    </div>
                    <div className="reports-page__sub-actions">
                      <button
                        className="schedules-list__item-btn"
                        onClick={() => handleSendNow(s.schedule_id)}
                        disabled={sendingId === s.schedule_id}
                      >
                        {sendingId === s.schedule_id
                          ? "Sending..."
                          : "Send Now"}
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
          </>
        )}

        {subscribingReport && (
          <ScheduleEmailDialog
            entityType="report"
            entityId={subscribingReport.report_id}
            widgets={[]}
            userEmail={user?.email ?? ""}
            onSave={() => {
              setSubscribingReport(null);
              fetchData();
            }}
            onCancel={() => setSubscribingReport(null)}
          />
        )}
      </div>
    </Layout>
  );
}
