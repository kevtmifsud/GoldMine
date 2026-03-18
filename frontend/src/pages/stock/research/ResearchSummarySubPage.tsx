import { EmbeddedChat } from "../../../components/chat/EmbeddedChat";
import { ResearchDocumentsGrid } from "../../../components/research/ResearchDocumentsGrid";
import { useStockEntity } from "../StockEntityPage";

export function ResearchSummarySubPage() {
  const { detail } = useStockEntity();

  return (
    <>
      <EmbeddedChat />
      <ResearchDocumentsGrid
      entityType={detail.entity_type}
      entityId={detail.entity_id}
        title="All Documents"
      />
    </>
  );
}
