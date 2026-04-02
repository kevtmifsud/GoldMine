import { TranscriptsGrid } from "../../../components/research/TranscriptsGrid";
import { useStockEntity } from "../StockEntityPage";

export function TranscriptsSubPage() {
  const { detail } = useStockEntity();

  return (
    <>
      <TranscriptsGrid symbol={detail.entity_id} />
    </>
  );
}
