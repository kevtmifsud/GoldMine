import { WidgetContainer } from "../../components/WidgetContainer";
import { DocumentsPanel } from "../../components/DocumentsPanel";
import { ResearchSearchBar } from "../../components/ResearchSearchBar";
import { useStockEntity } from "./StockEntityPage";

export function StockResearchSubPage() {
  const { detail, handleWidgetStateChange, getWidgetRef } = useStockEntity();

  const relatedFiles = detail.widgets.filter(
    (w) => w.widget_id === "related_files"
  );

  return (
    <div style={{ paddingTop: "1rem" }}>
      <ResearchSearchBar entityType={detail.entity_type} entityId={detail.entity_id} />
      {relatedFiles.map((widget) => (
        <WidgetContainer
          key={widget.widget_id}
          ref={getWidgetRef(widget.widget_id)}
          config={widget}
          entityId={detail.entity_id}
          onStateChange={handleWidgetStateChange}
        />
      ))}
      <div style={{ marginTop: "1.5rem" }}>
        <DocumentsPanel entityType={detail.entity_type} entityId={detail.entity_id} />
      </div>
    </div>
  );
}
