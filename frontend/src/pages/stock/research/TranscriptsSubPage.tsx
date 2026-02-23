import { ResearchSearchBar } from "../../../components/ResearchSearchBar";
import { TranscriptsGrid } from "../../../components/research/TranscriptsGrid";
import { useStockEntity } from "../StockEntityPage";

export function TranscriptsSubPage() {
  const { detail } = useStockEntity();

  return (
    <>
      <ResearchSearchBar
        entityType={detail.entity_type}
        entityId={detail.entity_id}
      />
      <TranscriptsGrid symbol={detail.entity_id} />
    </>
  );
}
