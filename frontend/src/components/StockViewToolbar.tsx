import { useState } from "react";
import type { WidgetConfig } from "../types/entities";
import { ScheduleEmailDialog } from "./ScheduleEmailDialog";
import { useStockEntity } from "../pages/stock/StockEntityPage";
import "../styles/entity.css";

interface StockViewToolbarProps {
  pageWidgets: WidgetConfig[];
}

export function StockViewToolbar({ pageWidgets }: StockViewToolbarProps) {
  const {
    detail,
    views,
    activeView,
    isViewOwner,
    viewId,
    handleViewSelect,
    handleDeleteView,
    collectOverrides,
    user,
    bumpSchedulesRefresh,
  } = useStockEntity();

  const [showScheduleDialog, setShowScheduleDialog] = useState(false);

  return (
    <>
      <div className="entity-page__top-bar">
        <div />
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
      </div>

      {showScheduleDialog && (
        <ScheduleEmailDialog
          entityType={detail.entity_type}
          entityId={detail.entity_id}
          widgets={pageWidgets}
          currentOverrides={collectOverrides()}
          userEmail={user?.email}
          onSave={() => {
            setShowScheduleDialog(false);
            bumpSchedulesRefresh();
          }}
          onCancel={() => setShowScheduleDialog(false)}
        />
      )}
    </>
  );
}
