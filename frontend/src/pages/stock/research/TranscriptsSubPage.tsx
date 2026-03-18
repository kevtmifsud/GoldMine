import { EmbeddedChat } from "../../../components/chat/EmbeddedChat";
import { TranscriptsGrid } from "../../../components/research/TranscriptsGrid";
import { useStockEntity } from "../StockEntityPage";

export function TranscriptsSubPage() {
  const { detail } = useStockEntity();

  return (
    <>
      <EmbeddedChat />
      <TranscriptsGrid symbol={detail.entity_id} />
    </>
  );
}
