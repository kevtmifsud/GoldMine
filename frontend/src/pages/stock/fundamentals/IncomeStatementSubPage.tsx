import { FinancialTable } from "../../../components/FinancialTable";
import { useStockEntity } from "../StockEntityPage";

export function IncomeStatementSubPage() {
  const { detail } = useStockEntity();
  return <FinancialTable ticker={detail.entity_id} statementType="income-statement" />;
}
