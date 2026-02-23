import { ResearchSearchBar } from "../../../components/ResearchSearchBar";
import { EarningsTranscriptsGrid } from "../../../components/research/EarningsTranscriptsGrid";
import { useStockEntity } from "../StockEntityPage";

export function EarningsTranscriptsSubPage() {
  const { detail } = useStockEntity();

  return (
    <>
      <ResearchSearchBar
        entityType={detail.entity_type}
        entityId={detail.entity_id}
      />
      <EarningsTranscriptsGrid symbol={detail.entity_id} />
    </>
  );
}
