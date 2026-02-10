import type { WidgetConfig } from "../types/entities";
import { ChartWidget } from "./ChartWidget";
import { SmartlistWidget } from "./SmartlistWidget";

interface WidgetContainerProps {
  config: WidgetConfig;
}

export function WidgetContainer({ config }: WidgetContainerProps) {
  if (config.widget_type === "chart") {
    return <ChartWidget config={config} />;
  }
  return <SmartlistWidget config={config} />;
}
