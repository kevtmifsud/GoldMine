import { ResearchSearchBar } from "../../components/ResearchSearchBar";
import { StockViewToolbar } from "../../components/StockViewToolbar";
import { useStockEntity } from "./StockEntityPage";

export function StockDataSubPage() {
  const { detail } = useStockEntity();

  return (
    <>
      <ResearchSearchBar entityType={detail.entity_type} entityId={detail.entity_id} />
      <StockViewToolbar pageWidgets={[]} />
      <div style={{ padding: "2rem 1.25rem", color: "var(--color-text-secondary)" }}>
        Data content will be added here.
      </div>
    </>
  );
}
