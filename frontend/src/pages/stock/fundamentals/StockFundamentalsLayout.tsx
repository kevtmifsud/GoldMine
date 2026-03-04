import { Outlet } from "react-router-dom";
import { useStockEntity } from "../StockEntityPage";

export function StockFundamentalsLayout() {
  const ctx = useStockEntity();
  return <Outlet context={ctx} />;
}
