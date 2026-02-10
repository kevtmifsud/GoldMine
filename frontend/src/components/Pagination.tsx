import "../styles/smartlist.css";

interface PaginationProps {
  page: number;
  totalPages: number;
  totalRecords: number;
  onPageChange: (page: number) => void;
}

export function Pagination({
  page,
  totalPages,
  totalRecords,
  onPageChange,
}: PaginationProps) {
  return (
    <div className="smartlist__pagination">
      <button
        className="smartlist__page-btn"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        Previous
      </button>
      <span className="smartlist__page-info">
        Page {page} of {totalPages} ({totalRecords} records)
      </span>
      <button
        className="smartlist__page-btn"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        Next
      </button>
    </div>
  );
}
