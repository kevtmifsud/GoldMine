/**
 * Date comparator for AG Grid's agDateColumnFilter.
 * Parses YYYY-MM-DD (or ISO 8601) date strings for proper date comparison.
 */
export function dateFilterComparator(
  filterLocalDateAtMidnight: Date,
  cellValue: string
): number {
  if (!cellValue) return -1;
  const parts = cellValue.substring(0, 10).split("-");
  const cellDate = new Date(
    Number(parts[0]),
    Number(parts[1]) - 1,
    Number(parts[2])
  );
  if (cellDate < filterLocalDateAtMidnight) return -1;
  if (cellDate > filterLocalDateAtMidnight) return 1;
  return 0;
}

/** Reusable filterParams for date columns using string-formatted dates. */
export const dateFilterParams = {
  comparator: dateFilterComparator,
};
