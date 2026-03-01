import { WidgetContainer } from "../../components/WidgetContainer";
import { ResearchSearchBar } from "../../components/ResearchSearchBar";
import { StockViewToolbar } from "../../components/StockViewToolbar";
import { useStockEntity } from "./StockEntityPage";

export function StockContactsSubPage() {
  const { detail, getWidgetRef } = useStockEntity();

  const relatedPeople = detail.widgets.filter(
    (w) => w.widget_id === "related_people"
  );

  return (
    <>
      <ResearchSearchBar entityType={detail.entity_type} entityId={detail.entity_id} />
      <StockViewToolbar pageWidgets={relatedPeople} />
      {relatedPeople.length > 0 ? (
        relatedPeople.map((widget) => (
          <WidgetContainer
            key={widget.widget_id}
            ref={getWidgetRef(widget.widget_id)}
            config={widget}
            entityId={detail.entity_id}
          />
        ))
      ) : (
        <div style={{ padding: "2rem 1.25rem", color: "var(--color-text-secondary)" }}>
          No contact data available for this entity.
        </div>
      )}
    </>
  );
}
