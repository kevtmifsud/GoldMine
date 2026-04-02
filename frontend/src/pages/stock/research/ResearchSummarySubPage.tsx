import { ResearchDocumentsGrid } from "../../../components/research/ResearchDocumentsGrid";
import { useStockEntity } from "../StockEntityPage";

export function ResearchSummarySubPage() {
  const { detail } = useStockEntity();

  return (
    <>
      <ResearchDocumentsGrid
      entityType={detail.entity_type}
      entityId={detail.entity_id}
        title="All Documents"
      />
    </>
  );
}
