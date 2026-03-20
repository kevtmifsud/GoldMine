import { useEffect, useState, useRef, useCallback, createRef } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import api from "../config/api";
import type { EntityDetail, SavedView, WidgetStateOverride } from "../types/entities";
import type { SmartlistWidgetHandle } from "../components/SmartlistWidget";
import { Layout } from "../components/Layout";
import { EntityHeader } from "../components/EntityHeader";
import { WidgetContainer } from "../components/WidgetContainer";
import { DocumentsPanel } from "../components/DocumentsPanel";

import { ScheduleEmailDialog } from "../components/ScheduleEmailDialog";
import { SchedulesList } from "../components/SchedulesList";
import { EntityPackSection } from "../components/EntityPackSection";
import { useAuth } from "../auth/useAuth";
import * as viewsApi from "../config/viewsApi";
import "../styles/entity.css";

export function EntityPage() {
  const { entityType, entityId } = useParams<{
    entityType: string;
    entityId: string;
  }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();

  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [views, setViews] = useState<SavedView[]>([]);
  const [showScheduleDialog, setShowScheduleDialog] = useState(false);
  const [schedulesRefreshKey, setSchedulesRefreshKey] = useState(0);

  const widgetRefs = useRef<Map<string, React.RefObject<SmartlistWidgetHandle>>>(new Map());

  const viewId = searchParams.get("view_id");

  // Fetch entity detail (re-fetches when viewId changes)
  useEffect(() => {
    if (!entityType || !entityId) return;

    setLoading(true);
    setError(null);
    setDetail(null);

    const params: Record<string, string> = {};
    if (viewId) params.view_id = viewId;

    api
      .get<EntityDetail>(`/api/entities/${entityType}/${entityId}`, { params })
      .then((resp) => {
        setDetail(resp.data);
      })
      .catch(() => {
        setError("Failed to load entity details");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [entityType, entityId, viewId]);

  // Fetch available views for this entity
  useEffect(() => {
    if (!entityType || !entityId) return;
    viewsApi.listViews(entityType, entityId).then(setViews).catch(() => {});
  }, [entityType, entityId]);

  const handleViewSelect = useCallback(
    (selectedViewId: string | null) => {
      if (selectedViewId) {
        setSearchParams({ view_id: selectedViewId });
      } else {
        setSearchParams({});
      }
    },
    [setSearchParams]
  );

  // Collect current widget state from all refs (used by email scheduling)
  const collectOverrides = useCallback((): WidgetStateOverride[] => {
    const overrides: WidgetStateOverride[] = [];
    for (const [, ref] of widgetRefs.current) {
      if (ref.current) {
        overrides.push(ref.current.getState());
      }
    }
    return overrides;
  }, []);

  const handleDeleteView = useCallback(
    async (deleteViewId: string) => {
      if (!entityType || !entityId) return;
      await viewsApi.deleteView(deleteViewId);
      const updated = await viewsApi.listViews(entityType, entityId);
      setViews(updated);
      setSearchParams({});
    },
    [entityType, entityId, setSearchParams]
  );

  // Build refs map for widgets
  const getWidgetRef = (widgetId: string) => {
    if (!widgetRefs.current.has(widgetId)) {
      widgetRefs.current.set(widgetId, createRef<SmartlistWidgetHandle>() as React.RefObject<SmartlistWidgetHandle>);
    }
    return widgetRefs.current.get(widgetId)!;
  };

  const activeView = detail?.active_view_id
    ? views.find((v) => v.view_id === detail.active_view_id)
    : null;
  const isViewOwner = activeView?.owner === (user?.username ?? "");

  return (
    <Layout>
      <div className="entity-page">
        <div className="entity-page__top-bar">
          <Link to={entityType === "dataset" || entityType === "portfolio" ? "/datasets" : "/"} className="entity-page__back">
            &larr; {entityType === "dataset" || entityType === "portfolio" ? "Back to Datasets" : "Back to Search"}
          </Link>
          {detail && (
            <div className="entity-page__actions">
              <select
                className="entity-page__view-select"
                value={viewId ?? ""}
                onChange={(e) => handleViewSelect(e.target.value || null)}
              >
                <option value="">
                  Default View{views.some((v) => v.is_default && v.owner === (user?.username ?? "")) ? " (customized)" : ""}
                </option>
                {views.filter((v) => !v.is_default).map((v) => (
                  <option key={v.view_id} value={v.view_id}>
                    {v.name}{v.owner !== (user?.username ?? "") ? ` (${v.owner})` : ""}
                  </option>
                ))}
              </select>
              {isViewOwner && !activeView?.is_default && (
                <button
                  className="entity-page__action-btn entity-page__action-btn--danger"
                  onClick={() => handleDeleteView(detail.active_view_id!)}
                >
                  Delete
                </button>
              )}
              <button
                className="entity-page__action-btn entity-page__action-btn--primary"
                onClick={() => setShowScheduleDialog(true)}
              >
                Create Alert
              </button>
            </div>
          )}
        </div>
        {loading && (
          <div className="entity-page__loading">
            <div className="spinner" />
          </div>
        )}
        {error && <div className="entity-page__error">{error}</div>}
        {detail && (
          <>
            <EntityHeader
              displayName={detail.display_name}
              entityType={detail.entity_type}
              headerFields={detail.header_fields}
            />
            <div className="entity-page__widgets">
              {detail.widgets
                .filter((w) => w.widget_type === "chart" && w.full_width)
                .map((widget) => (
                  <div key={widget.widget_id} className="entity-page__chart-full">
                    <WidgetContainer
                      ref={getWidgetRef(widget.widget_id)}
                      config={widget}
                      entityId={detail.entity_id}
                    />
                  </div>
                ))}
              {detail.widgets.some((w) => (w.widget_type === "chart" || w.widget_type === "top_positions") && !w.full_width) && (
                <div className="entity-page__charts">
                  {detail.widgets
                    .filter((w) => (w.widget_type === "chart" || w.widget_type === "top_positions") && !w.full_width)
                    .map((widget) => (
                      <WidgetContainer
                        key={widget.widget_id}
                        ref={getWidgetRef(widget.widget_id)}
                        config={widget}
                        entityId={detail.entity_id}
                      />
                    ))}
                </div>
              )}
              {detail.widgets
                .filter((w) => w.widget_type !== "chart" && w.widget_type !== "top_positions")
                .map((widget) => (
                  <WidgetContainer
                    key={widget.widget_id}
                    ref={getWidgetRef(widget.widget_id)}
                    config={widget}
                    entityId={detail.entity_id}
                  />
                ))}
            </div>
            {detail.entity_type !== "dataset" && detail.entity_type !== "portfolio" && (
              <>
                <div className="entity-page__documents">
                  <DocumentsPanel entityType={detail.entity_type} entityId={detail.entity_id} />
                </div>
                <div className="entity-page__schedules">
                  <SchedulesList
                    entityType={detail.entity_type}
                    entityId={detail.entity_id}
                    refreshKey={schedulesRefreshKey}
                  />
                </div>
              </>
            )}
            <EntityPackSection entityType={detail.entity_type} entityId={detail.entity_id} />
          </>
        )}
        {showScheduleDialog && detail && (
          <ScheduleEmailDialog
            entityType={detail.entity_type}
            entityId={detail.entity_id}
            widgets={detail.widgets}
            currentOverrides={collectOverrides()}
            userEmail={user?.email}
            onSave={() => {
              setShowScheduleDialog(false);
              setSchedulesRefreshKey((k) => k + 1);
            }}
            onCancel={() => setShowScheduleDialog(false)}
          />
        )}
      </div>
    </Layout>
  );
}
