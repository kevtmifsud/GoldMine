import { forwardRef } from "react";
import type { WidgetConfig } from "../types/entities";
import { ChartWidget } from "./ChartWidget";
import { SmartlistWidget } from "./SmartlistWidget";
import type { SmartlistWidgetHandle } from "./SmartlistWidget";

interface WidgetContainerProps {
  config: WidgetConfig;
  entityId?: string;
}

export const WidgetContainer = forwardRef<SmartlistWidgetHandle, WidgetContainerProps>(
  function WidgetContainer({ config, entityId }, ref) {
    if (config.widget_type === "chart") {
      return <ChartWidget config={config} entityId={entityId} />;
    }
    return <SmartlistWidget ref={ref} config={config} />;
  }
);
