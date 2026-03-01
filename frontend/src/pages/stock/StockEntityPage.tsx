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
  viewId: string | null;
  schedulesRefreshKey: number;
  handleViewSelect: (viewId: string | null) => void;
  handleDeleteView: (viewId: string) => Promise<void>;
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

  const widgetRefs = useRef<Map<string, React.RefObject<SmartlistWidgetHandle>>>(new Map());

  const viewId = searchParams.get("view_id");

  useEffect(() => {
    if (!entityId) return;

    setLoading(true);
    setError(null);
    setDetail(null);

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
    viewId,
    schedulesRefreshKey,
    handleViewSelect,
    handleDeleteView,
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
