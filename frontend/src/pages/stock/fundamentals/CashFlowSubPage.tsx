import { FinancialTable } from "../../../components/FinancialTable";
import { useStockEntity } from "../StockEntityPage";

export function CashFlowSubPage() {
  const { detail } = useStockEntity();
  return <FinancialTable ticker={detail.entity_id} statementType="cash-flow" />;
}
