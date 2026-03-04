import api from "./api";
import type { FinancialStatementResponse } from "../types/financials";

export function getFiscalQuarter(dateStr: string, fyEndMonth: number): number {
  const d = new Date(dateStr + "T00:00:00");
  const month = d.getUTCMonth() + 1;
  const offset = ((month - fyEndMonth - 1 + 12) % 12) + 1;
  return Math.ceil(offset / 3);
}

export function formatDateLabel(dateStr: string, period: string, fyEndMonth: number): string {
  const d = new Date(dateStr + "T00:00:00");
  const year = d.getUTCFullYear();
  const month = d.getUTCMonth() + 1;

  if (period === "annual") {
    return `FY${year}`;
  }

  // Fiscal quarter: offset 1-12 from FY start, then ceil(offset/3) = quarter
  const offset = ((month - fyEndMonth - 1 + 12) % 12) + 1;
  const quarter = Math.ceil(offset / 3);
  const fy = month > fyEndMonth ? year + 1 : year;
  const fyShort = String(fy).slice(-2);
  return `${quarter}Q${fyShort}`;
}

interface CombinedColumn {
  date: string;
  source: "quarterly" | "annual";
  label: string;
}

function buildCombinedColumns(
  quarterlyDates: string[],
  annualDates: string[],
  fyEndMonth: number,
): CombinedColumn[] {
  const annualDateSet = new Set(annualDates);
  const usedAnnualDates = new Set<string>();
  const columns: CombinedColumn[] = [];

  for (const d of quarterlyDates) {
    columns.push({
      date: d,
      source: "quarterly",
      label: formatDateLabel(d, "quarterly", fyEndMonth),
    });
    if (getFiscalQuarter(d, fyEndMonth) === 4 && annualDateSet.has(d)) {
      columns.push({
        date: d,
        source: "annual",
        label: formatDateLabel(d, "annual", fyEndMonth),
      });
      usedAnnualDates.add(d);
    }
  }

  // Prepend any annual dates not covered by quarterly Q4
  const extraAnnual = annualDates
    .filter((d) => !usedAnnualDates.has(d))
    .map((d) => ({
      date: d,
      source: "annual" as const,
      label: formatDateLabel(d, "annual", fyEndMonth),
    }));

  return [...extraAnnual, ...columns];
}

export async function downloadFinancialsExcel(ticker: string) {
  const XLSX = await import("xlsx");

  const [isQ, isA, bsQ, bsA, cfQ, cfA] = await Promise.all([
    api.get<FinancialStatementResponse>(`/api/financials/${ticker}/income-statement`, { params: { period: "quarterly" } }),
    api.get<FinancialStatementResponse>(`/api/financials/${ticker}/income-statement`, { params: { period: "annual" } }),
    api.get<FinancialStatementResponse>(`/api/financials/${ticker}/balance-sheet`, { params: { period: "quarterly" } }),
    api.get<FinancialStatementResponse>(`/api/financials/${ticker}/balance-sheet`, { params: { period: "annual" } }),
    api.get<FinancialStatementResponse>(`/api/financials/${ticker}/cash-flow`, { params: { period: "quarterly" } }),
    api.get<FinancialStatementResponse>(`/api/financials/${ticker}/cash-flow`, { params: { period: "annual" } }),
  ]);

  const fyEndMonth = isA.data.fy_end_month;
  const wb = XLSX.utils.book_new();

  for (const { quarterly, annual, name } of [
    { quarterly: isQ.data, annual: isA.data, name: "Income Statement" },
    { quarterly: bsQ.data, annual: bsA.data, name: "Balance Sheet" },
    { quarterly: cfQ.data, annual: cfA.data, name: "Cash Flow" },
  ]) {
    const columns = buildCombinedColumns(quarterly.dates, annual.dates, fyEndMonth);
    const headers: (string | null)[] = ["", ...columns.map((c) => c.label)];
    const rows: (string | number | null)[][] = [headers];

    const annualItemMap = new Map(annual.line_items.map((i) => [i.metric, i]));
    const baseItems = quarterly.line_items.length > 0 ? quarterly.line_items : annual.line_items;

    for (const item of baseItems) {
      const indent = "  ".repeat(item.indent);
      const row: (string | number | null)[] = [indent + item.label];
      const annualItem = annualItemMap.get(item.metric);

      for (const col of columns) {
        if (col.source === "annual") {
          row.push(annualItem?.values[col.date] ?? null);
        } else {
          row.push(item.values[col.date] ?? null);
        }
      }
      rows.push(row);
    }

    const ws = XLSX.utils.aoa_to_sheet(rows);
    XLSX.utils.book_append_sheet(wb, ws, name);
  }

  XLSX.writeFile(wb, `${ticker}_financials.xlsx`);
}
