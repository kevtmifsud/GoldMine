import { useEffect, useState, useRef, useCallback, createRef } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import api from "../config/api";
import type { EntityDetail, SavedView, WidgetStateOverride } from "../types/entities";
import type { SmartlistWidgetHandle } from "../components/SmartlistWidget";
import { Layout } from "../components/Layout";
import { EntityHeader } from "../components/EntityHeader";
import { WidgetContainer } from "../components/WidgetContainer";
import { ViewToolbar } from "../components/ViewToolbar";
import { SaveViewDialog } from "../components/SaveViewDialog";
import { DocumentsPanel } from "../components/DocumentsPanel";
import { LLMQueryPanel } from "../components/LLMQueryPanel";
import { ScheduleEmailDialog } from "../components/ScheduleEmailDialog";
import { SchedulesList } from "../components/SchedulesList";
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
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [showScheduleDialog, setShowScheduleDialog] = useState(false);
  const [schedulePreSelectedWidget, setSchedulePreSelectedWidget] = useState<string | null>(null);
  const [schedulesRefreshKey, setSchedulesRefreshKey] = useState(0);
  const [dirty, setDirty] = useState(false);

  const widgetRefs = useRef<Map<string, React.RefObject<SmartlistWidgetHandle>>>(new Map());

  const viewId = searchParams.get("view_id");

  // Fetch entity detail (re-fetches when viewId changes)
  useEffect(() => {
    if (!entityType || !entityId) return;

    setLoading(true);
    setError(null);
    setDetail(null);
    setDirty(false);

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

  // Collect current widget state from all refs
  const collectOverrides = useCallback((): WidgetStateOverride[] => {
    const overrides: WidgetStateOverride[] = [];
    for (const [, ref] of widgetRefs.current) {
      if (ref.current) {
        overrides.push(ref.current.getState());
      }
    }
    return overrides;
  }, []);

  // Save as a new view (opens dialog)
  const handleSaveNewView = useCallback(
    async (name: string, isShared: boolean) => {
      if (!entityType || !entityId) return;

      const overrides = collectOverrides();
      const view = await viewsApi.createView({
        name,
        entity_type: entityType,
        entity_id: entityId,
        widget_overrides: overrides,
        is_shared: isShared,
      });

      setShowSaveDialog(false);
      const updated = await viewsApi.listViews(entityType, entityId);
      setViews(updated);
      setSearchParams({ view_id: view.view_id });
    },
    [entityType, entityId, setSearchParams, collectOverrides]
  );

  // Overwrite the currently active view in-place
  const handleOverwriteView = useCallback(async () => {
    if (!entityType || !entityId || !viewId) return;

    const overrides = collectOverrides();
    await viewsApi.updateView(viewId, { widget_overrides: overrides });

    // Re-fetch to get the merged detail with updated overrides
    setDirty(false);
    const params: Record<string, string> = { view_id: viewId };
    const resp = await api.get<EntityDetail>(
      `/api/entities/${entityType}/${entityId}`,
      { params }
    );
    setDetail(resp.data);
  }, [entityType, entityId, viewId, collectOverrides]);

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

  const handleWidgetStateChange = useCallback(() => {
    setDirty(true);
  }, []);

  // Build refs map for widgets
  const getWidgetRef = (widgetId: string) => {
    if (!widgetRefs.current.has(widgetId)) {
      widgetRefs.current.set(widgetId, createRef<SmartlistWidgetHandle>() as React.RefObject<SmartlistWidgetHandle>);
    }
    return widgetRefs.current.get(widgetId)!;
  };

  return (
    <Layout>
      <div className="entity-page">
        <Link to="/" className="entity-page__back">
          &larr; Back to Search
        </Link>
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
            <ViewToolbar
              entityType={detail.entity_type}
              entityId={detail.entity_id}
              activeViewId={detail.active_view_id}
              activeViewName={detail.active_view_name}
              views={views}
              currentUser={user?.username ?? ""}
              dirty={dirty}
              onViewSelect={handleViewSelect}
              onOverwriteView={handleOverwriteView}
              onSaveNewView={() => setShowSaveDialog(true)}
              onDeleteView={handleDeleteView}
            />
            <button
              className="entity-page__schedule-btn"
              onClick={() => {
                setSchedulePreSelectedWidget(null);
                setShowScheduleDialog(true);
              }}
            >
              Schedule Email
            </button>
            <div className="entity-page__widgets">
              {detail.widgets.map((widget) => (
                <WidgetContainer
                  key={widget.widget_id}
                  ref={getWidgetRef(widget.widget_id)}
                  config={widget}
                  onStateChange={handleWidgetStateChange}
                />
              ))}
            </div>
            <div className="entity-page__documents">
              <DocumentsPanel entityType={detail.entity_type} entityId={detail.entity_id} />
            </div>
            <div className="entity-page__llm">
              <LLMQueryPanel entityType={detail.entity_type} entityId={detail.entity_id} />
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
        {showSaveDialog && (
          <SaveViewDialog
            onSave={handleSaveNewView}
            onCancel={() => setShowSaveDialog(false)}
          />
        )}
        {showScheduleDialog && detail && (
          <ScheduleEmailDialog
            entityType={detail.entity_type}
            entityId={detail.entity_id}
            widgets={detail.widgets}
            preSelectedWidgetId={schedulePreSelectedWidget}
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
