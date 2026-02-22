import { WidgetContainer } from "../../components/WidgetContainer";
import { ResearchSearchBar } from "../../components/ResearchSearchBar";
import { useStockEntity } from "./StockEntityPage";

export function StockContactsSubPage() {
  const { detail, handleWidgetStateChange, getWidgetRef } = useStockEntity();

  const relatedPeople = detail.widgets.filter(
    (w) => w.widget_id === "related_people"
  );

  return (
    <div style={{ paddingTop: "1rem" }}>
      <ResearchSearchBar entityType={detail.entity_type} entityId={detail.entity_id} />
      {relatedPeople.length > 0 ? (
        relatedPeople.map((widget) => (
          <WidgetContainer
            key={widget.widget_id}
            ref={getWidgetRef(widget.widget_id)}
            config={widget}
            entityId={detail.entity_id}
            onStateChange={handleWidgetStateChange}
          />
        ))
      ) : (
        <div>
          <h2 style={{ fontSize: "1.25rem", fontWeight: 600, marginBottom: "0.5rem" }}>
            Contacts
          </h2>
          <p style={{ color: "var(--color-text-secondary)" }}>
            No contact data available for this entity.
          </p>
        </div>
      )}
    </div>
  );
}
