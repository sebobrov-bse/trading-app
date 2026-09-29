interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onOffsetChange: (offset: number) => void;
}

export function Pagination({
  total,
  limit,
  offset,
  onOffsetChange,
}: PaginationProps) {
  if (total === 0) return null;

  const from = offset + 1;
  const to = Math.min(offset + limit, total);
  const canPrev = offset > 0;
  const canNext = offset + limit < total;

  return (
    <div className="pagination">
      <span className="muted">
        Showing {from}–{to} of {total}
      </span>
      <div className="pagination-buttons">
        <button
          type="button"
          disabled={!canPrev}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
        >
          ← Prev
        </button>
        <button
          type="button"
          disabled={!canNext}
          onClick={() => onOffsetChange(offset + limit)}
        >
          Next →
        </button>
      </div>
    </div>
  );
}