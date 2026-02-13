import { forwardRef } from "react";
import type { WidgetConfig } from "../types/entities";
import { ChartWidget } from "./ChartWidget";
import { SmartlistWidget } from "./SmartlistWidget";
import type { SmartlistWidgetHandle } from "./SmartlistWidget";

interface WidgetContainerProps {
  config: WidgetConfig;
  entityId?: string;
  onStateChange?: () => void;
}

export const WidgetContainer = forwardRef<SmartlistWidgetHandle, WidgetContainerProps>(
  function WidgetContainer({ config, entityId, onStateChange }, ref) {
    if (config.widget_type === "chart") {
      return <ChartWidget config={config} entityId={entityId} />;
    }
    return <SmartlistWidget ref={ref} config={config} onStateChange={onStateChange} />;
  }
);
