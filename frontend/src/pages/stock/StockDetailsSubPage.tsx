import { EntityHeader } from "../../components/EntityHeader";
import { WidgetContainer } from "../../components/WidgetContainer";
import { SaveViewDialog } from "../../components/SaveViewDialog";
import { ScheduleEmailDialog } from "../../components/ScheduleEmailDialog";
import { ResearchSearchBar } from "../../components/ResearchSearchBar";
import { useStockEntity } from "./StockEntityPage";
import "../../styles/entity.css";

export function StockDetailsSubPage() {
  const {
    detail,
    views,
    isViewOwner,
    dirty,
    handleViewSelect,
    handleSaveNewView,
    handleOverwriteView,
    handleDeleteView,
    handleWidgetStateChange,
    getWidgetRef,
    collectOverrides,
    setShowSaveDialog,
    setShowScheduleDialog,
    showSaveDialog,
    showScheduleDialog,
    user,
    bumpSchedulesRefresh,
  } = useStockEntity();

  const chartWidgets = detail.widgets.filter((w) => w.widget_type === "chart");
  const priceHistory = chartWidgets.filter((w) => w.widget_id === "price_history");
  const otherCharts = chartWidgets.filter((w) => w.widget_id !== "price_history");

  return (
    <>
      <ResearchSearchBar entityType={detail.entity_type} entityId={detail.entity_id} />
      <div className="entity-page__top-bar">
        <div />
        <div className="entity-page__actions">
          <select
            className="entity-page__view-select"
            value={detail.active_view_id ?? ""}
            onChange={(e) => handleViewSelect(e.target.value || null)}
          >
            <option value="">Default View</option>
            {views.map((v) => (
              <option key={v.view_id} value={v.view_id}>
                {v.name}{v.owner !== (user?.username ?? "") ? ` (${v.owner})` : ""}
              </option>
            ))}
          </select>
          {isViewOwner && (
            <button
              className="entity-page__action-btn entity-page__action-btn--danger"
              onClick={() => handleDeleteView(detail.active_view_id!)}
            >
              Delete
            </button>
          )}
          {dirty && isViewOwner && (
            <button
              className="entity-page__action-btn"
              onClick={handleOverwriteView}
            >
              Save
            </button>
          )}
          {dirty && (
            <button
              className="entity-page__action-btn"
              onClick={() => setShowSaveDialog(true)}
            >
              Save As New
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

      <EntityHeader
        displayName={detail.display_name}
        entityType={detail.entity_type}
        headerFields={detail.header_fields}
      />

      <div className="entity-page__widgets">
        {priceHistory.map((widget) => (
          <div key={widget.widget_id} className="entity-page__chart-full">
            <WidgetContainer
              ref={getWidgetRef(widget.widget_id)}
              config={widget}
              entityId={detail.entity_id}
              onStateChange={handleWidgetStateChange}
            />
          </div>
        ))}
        {otherCharts.length > 0 && (
          <div className="entity-page__charts">
            {otherCharts.map((widget) => (
              <WidgetContainer
                key={widget.widget_id}
                ref={getWidgetRef(widget.widget_id)}
                config={widget}
                entityId={detail.entity_id}
                onStateChange={handleWidgetStateChange}
              />
            ))}
          </div>
        )}
      </div>

      {showSaveDialog && (
        <SaveViewDialog
          onSave={handleSaveNewView}
          onCancel={() => setShowSaveDialog(false)}
        />
      )}
      {showScheduleDialog && (
        <ScheduleEmailDialog
          entityType={detail.entity_type}
          entityId={detail.entity_id}
          widgets={detail.widgets}
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
