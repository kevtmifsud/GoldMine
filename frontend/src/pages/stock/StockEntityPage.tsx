import { useEffect, useState, useRef, useCallback, createRef } from "react";
import { useParams, Outlet, useSearchParams, useOutletContext } from "react-router-dom";
import api from "../../config/api";
import type { EntityDetail, SavedView, WidgetStateOverride } from "../../types/entities";
import type { SmartlistWidgetHandle } from "../../components/SmartlistWidget";
import { Layout } from "../../components/Layout";
import { StockSidebar } from "../../components/StockSidebar";
import { useAuth } from "../../auth/useAuth";
import * as viewsApi from "../../config/viewsApi";
import "../../styles/stock-entity.css";

export interface StockEntityContext {
  detail: EntityDetail;
  views: SavedView[];
  activeView: SavedView | null;
  isViewOwner: boolean;
  dirty: boolean;
  viewId: string | null;
  schedulesRefreshKey: number;
  handleViewSelect: (viewId: string | null) => void;
  handleSaveNewView: (name: string, isShared: boolean) => Promise<void>;
  handleSaveView: () => Promise<void>;
  handleDeleteView: (viewId: string) => Promise<void>;
  handleWidgetStateChange: () => void;
  getWidgetRef: (widgetId: string) => React.RefObject<SmartlistWidgetHandle>;
  collectOverrides: () => WidgetStateOverride[];
  user: ReturnType<typeof useAuth>["user"];
  bumpSchedulesRefresh: () => void;
}

export function useStockEntity() {
  return useOutletContext<StockEntityContext>();
}

export function StockEntityPage() {
  const { entityId } = useParams<{ entityId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();

  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [views, setViews] = useState<SavedView[]>([]);
  const [schedulesRefreshKey, setSchedulesRefreshKey] = useState(0);
  const [dirty, setDirty] = useState(false);

  const widgetRefs = useRef<Map<string, React.RefObject<SmartlistWidgetHandle>>>(new Map());

  const viewId = searchParams.get("view_id");

  useEffect(() => {
    if (!entityId) return;

    setLoading(true);
    setError(null);
    setDetail(null);
    setDirty(false);

    const params: Record<string, string> = {};
    if (viewId) params.view_id = viewId;

    api
      .get<EntityDetail>(`/api/entities/stock/${entityId}`, { params })
      .then((resp) => setDetail(resp.data))
      .catch(() => setError("Failed to load entity details"))
      .finally(() => setLoading(false));
  }, [entityId, viewId]);

  useEffect(() => {
    if (!entityId) return;
    viewsApi.listViews("stock", entityId).then(setViews).catch(() => {});
  }, [entityId]);

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

  const collectOverrides = useCallback((): WidgetStateOverride[] => {
    const overrides: WidgetStateOverride[] = [];
    for (const [, ref] of widgetRefs.current) {
      if (ref.current) {
        overrides.push(ref.current.getState());
      }
    }
    return overrides;
  }, []);

  const handleSaveNewView = useCallback(
    async (name: string, isShared: boolean) => {
      if (!entityId) return;

      const overrides = collectOverrides();
      const view = await viewsApi.createView({
        name,
        entity_type: "stock",
        entity_id: entityId,
        widget_overrides: overrides,
        is_shared: isShared,
      });

      const updated = await viewsApi.listViews("stock", entityId);
      setViews(updated);
      setSearchParams({ view_id: view.view_id });
    },
    [entityId, setSearchParams, collectOverrides]
  );

  // Silently save over the current view (owned view or default)
  const handleSaveView = useCallback(async () => {
    if (!entityId) return;

    const overrides = collectOverrides();
    const activeId = detail?.active_view_id;

    if (activeId) {
      // Overwrite the currently active view in-place
      await viewsApi.updateView(activeId, { widget_overrides: overrides });
    } else {
      // No active view — create a default view for this entity
      await viewsApi.createView({
        name: "Default",
        entity_type: "stock",
        entity_id: entityId,
        widget_overrides: overrides,
        is_shared: false,
        is_default: true,
      });
      const updated = await viewsApi.listViews("stock", entityId);
      setViews(updated);
    }

    // Re-fetch entity detail (backend auto-applies default view when no view_id)
    setDirty(false);
    const params: Record<string, string> = {};
    if (viewId) params.view_id = viewId;
    const resp = await api.get<EntityDetail>(`/api/entities/stock/${entityId}`, { params });
    setDetail(resp.data);
  }, [entityId, viewId, detail?.active_view_id, collectOverrides]);

  const handleDeleteView = useCallback(
    async (deleteViewId: string) => {
      if (!entityId) return;
      await viewsApi.deleteView(deleteViewId);
      const updated = await viewsApi.listViews("stock", entityId);
      setViews(updated);
      setSearchParams({});
    },
    [entityId, setSearchParams]
  );

  const handleWidgetStateChange = useCallback(() => {
    setDirty(true);
  }, []);

  const getWidgetRef = (widgetId: string) => {
    if (!widgetRefs.current.has(widgetId)) {
      widgetRefs.current.set(widgetId, createRef<SmartlistWidgetHandle>() as React.RefObject<SmartlistWidgetHandle>);
    }
    return widgetRefs.current.get(widgetId)!;
  };

  const bumpSchedulesRefresh = useCallback(() => {
    setSchedulesRefreshKey((k) => k + 1);
  }, []);

  const activeView = detail?.active_view_id
    ? views.find((v) => v.view_id === detail.active_view_id) ?? null
    : null;
  const isViewOwner = activeView?.owner === (user?.username ?? "");

  if (loading) {
    return (
      <Layout contentClassName="stock-entity-layout">
        <div className="stock-entity">
          <div className="stock-entity__loading">
            <div className="spinner" />
          </div>
        </div>
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout contentClassName="stock-entity-layout">
        <div className="stock-entity">
          <div className="stock-entity__error">{error}</div>
        </div>
      </Layout>
    );
  }

  if (!detail) return null;

  const context: StockEntityContext = {
    detail,
    views,
    activeView,
    isViewOwner,
    dirty,
    viewId,
    schedulesRefreshKey,
    handleViewSelect,
    handleSaveNewView,
    handleSaveView,
    handleDeleteView,
    handleWidgetStateChange,
    getWidgetRef,
    collectOverrides,
    user,
    bumpSchedulesRefresh,
  };

  return (
    <Layout contentClassName="stock-entity-layout">
      <div className="stock-entity">
        <StockSidebar displayName={detail.display_name} entityId={detail.entity_id} />
        <div className="stock-content">
          <Outlet context={context} />
        </div>
      </div>
    </Layout>
  );
}
