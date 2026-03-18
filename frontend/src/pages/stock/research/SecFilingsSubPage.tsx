import { EmbeddedChat } from "../../../components/chat/EmbeddedChat";
import { SecFilingsGrid } from "../../../components/research/SecFilingsGrid";
import { useStockEntity } from "../StockEntityPage";

export function SecFilingsSubPage() {
  const { detail } = useStockEntity();

  return (
    <>
      <EmbeddedChat />
      <SecFilingsGrid symbol={detail.entity_id} />
    </>
  );
}
