import { ResearchSearchBar } from "../../../components/ResearchSearchBar";
import { SecFilingsGrid } from "../../../components/research/SecFilingsGrid";
import { useStockEntity } from "../StockEntityPage";

export function SecFilingsSubPage() {
  const { detail } = useStockEntity();

  return (
    <>
      <ResearchSearchBar
        entityType={detail.entity_type}
        entityId={detail.entity_id}
      />
      <SecFilingsGrid symbol={detail.entity_id} />
    </>
  );
}
