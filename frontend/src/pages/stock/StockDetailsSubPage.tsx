import { WidgetContainer } from "../../components/WidgetContainer";
import { StockSummaryBar } from "../../components/StockSummaryBar";
import { StockViewToolbar } from "../../components/StockViewToolbar";
import { useStockEntity } from "./StockEntityPage";

export function StockDetailsSubPage() {
  const { detail, getWidgetRef } = useStockEntity();

  const chartWidgets = detail.widgets.filter((w) => w.widget_type === "chart");
  const priceHistory = chartWidgets.filter((w) => w.widget_id === "price_history");
  const otherCharts = chartWidgets.filter((w) => w.widget_id !== "price_history");

  return (
    <>
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
        />
      ))}
      {otherCharts.map((widget) => (
        <WidgetContainer
          key={widget.widget_id}
          ref={getWidgetRef(widget.widget_id)}
          config={widget}
          entityId={detail.entity_id}
        />
      ))}
    </>
  );
}
