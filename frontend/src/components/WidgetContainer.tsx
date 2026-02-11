import { forwardRef } from "react";
import type { WidgetConfig } from "../types/entities";
import { ChartWidget } from "./ChartWidget";
import { SmartlistWidget } from "./SmartlistWidget";
import type { SmartlistWidgetHandle } from "./SmartlistWidget";

interface WidgetContainerProps {
  config: WidgetConfig;
  onStateChange?: () => void;
}

export const WidgetContainer = forwardRef<SmartlistWidgetHandle, WidgetContainerProps>(
  function WidgetContainer({ config, onStateChange }, ref) {
    if (config.widget_type === "chart") {
      return <ChartWidget config={config} />;
    }
    return <SmartlistWidget ref={ref} config={config} onStateChange={onStateChange} />;
  }
);
