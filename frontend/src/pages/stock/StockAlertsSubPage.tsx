import { SchedulesList } from "../../components/SchedulesList";
import { ResearchSearchBar } from "../../components/ResearchSearchBar";
import { useStockEntity } from "./StockEntityPage";

export function StockAlertsSubPage() {
  const { detail, schedulesRefreshKey } = useStockEntity();

  return (
    <div style={{ paddingTop: "1rem" }}>
      <ResearchSearchBar entityType={detail.entity_type} entityId={detail.entity_id} />
      <SchedulesList
        entityType={detail.entity_type}
        entityId={detail.entity_id}
        refreshKey={schedulesRefreshKey}
      />
    </div>
  );
}
