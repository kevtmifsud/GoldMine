import { forwardRef } from "react";
import type { WidgetConfig } from "../types/entities";
import { PlotlyChartWidget } from "./PlotlyChartWidget";
import { SmartlistWidget } from "./SmartlistWidget";
import type { SmartlistWidgetHandle } from "./SmartlistWidget";
import { TopPositionsWidget } from "./TopPositionsWidget";

interface WidgetContainerProps {
  config: WidgetConfig;
  entityId?: string;
}

export const WidgetContainer = forwardRef<SmartlistWidgetHandle, WidgetContainerProps>(
  function WidgetContainer({ config, entityId }, ref) {
    if (config.widget_type === "chart") {
      return <PlotlyChartWidget config={config} entityId={entityId} />;
    }
    if (config.widget_type === "top_positions") {
      return <TopPositionsWidget config={config} />;
    }
    return <SmartlistWidget ref={ref} config={config} />;
  }
);
