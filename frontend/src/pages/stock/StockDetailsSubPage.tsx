import { WidgetContainer } from "../../components/WidgetContainer";
import { ResearchSearchBar } from "../../components/ResearchSearchBar";
import { StockSummaryBar } from "../../components/StockSummaryBar";
import { StockViewToolbar } from "../../components/StockViewToolbar";
import { useStockEntity } from "./StockEntityPage";

export function StockDetailsSubPage() {
  const { detail, handleWidgetStateChange, getWidgetRef } = useStockEntity();

  const chartWidgets = detail.widgets.filter((w) => w.widget_type === "chart");
  const priceHistory = chartWidgets.filter((w) => w.widget_id === "price_history");
  const otherCharts = chartWidgets.filter((w) => w.widget_id !== "price_history");

  return (
    <>
      <ResearchSearchBar entityType={detail.entity_type} entityId={detail.entity_id} />
      <StockViewToolbar pageWidgets={chartWidgets} />

      <StockSummaryBar
        displayName={detail.display_name}
        headerFields={detail.header_fields}
      />

      {priceHistory.map((widget) => (
        <WidgetContainer
          key={widget.widget_id}
          ref={getWidgetRef(widget.widget_id)}
          config={widget}
          entityId={detail.entity_id}
          onStateChange={handleWidgetStateChange}
        />
      ))}
      {otherCharts.map((widget) => (
        <WidgetContainer
          key={widget.widget_id}
          ref={getWidgetRef(widget.widget_id)}
          config={widget}
          entityId={detail.entity_id}
          onStateChange={handleWidgetStateChange}
        />
      ))}
    </>
  );
}
