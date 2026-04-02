import { StockViewToolbar } from "../../components/StockViewToolbar";
import { useStockEntity } from "./StockEntityPage";

export function StockDataSubPage() {
  const { detail: _detail } = useStockEntity();

  return (
    <>
      <StockViewToolbar pageWidgets={[]} />
      <div style={{ padding: "2rem 1.25rem", color: "var(--color-text-secondary)" }}>
        Data content will be added here.
      </div>
    </>
  );
}
