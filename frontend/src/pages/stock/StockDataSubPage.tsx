import { ResearchSearchBar } from "../../components/ResearchSearchBar";
import { useStockEntity } from "./StockEntityPage";

export function StockDataSubPage() {
  const { detail } = useStockEntity();

  return (
    <div style={{ paddingTop: "1rem" }}>
      <ResearchSearchBar entityType={detail.entity_type} entityId={detail.entity_id} />
      <h2 style={{ fontSize: "1.25rem", fontWeight: 600, marginBottom: "0.5rem" }}>
        Data
      </h2>
      <p style={{ color: "var(--color-text-secondary)" }}>
        Data content will be added here.
      </p>
    </div>
  );
}
