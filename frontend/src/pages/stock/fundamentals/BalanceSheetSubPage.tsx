import { FinancialTable } from "../../../components/FinancialTable";
import { useStockEntity } from "../StockEntityPage";

export function BalanceSheetSubPage() {
  const { detail } = useStockEntity();
  return <FinancialTable ticker={detail.entity_id} statementType="balance-sheet" />;
}
