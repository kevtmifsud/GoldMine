import { Outlet } from "react-router-dom";
import { useStockEntity } from "../StockEntityPage";

export function StockResearchLayout() {
  const ctx = useStockEntity();
  return <Outlet context={ctx} />;
}
