import { SchedulesList } from "../../components/SchedulesList";
import { StockViewToolbar } from "../../components/StockViewToolbar";
import { useStockEntity } from "./StockEntityPage";

export function StockAlertsSubPage() {
  const { detail, schedulesRefreshKey } = useStockEntity();

  return (
    <>
      <StockViewToolbar pageWidgets={[]} />
      <SchedulesList
        entityType={detail.entity_type}
        entityId={detail.entity_id}
        refreshKey={schedulesRefreshKey}
      />
    </>
  );
}
