import type { DataSummaryItem } from '../api/types';

interface DataSummaryTableProps {
  items: DataSummaryItem[];
  onDelete: (symbol: string, timeframe: number) => void;
}

function fmtDate(s: string): string {
  return s.slice(0, 10);
}

function fmtNumber(n: number): string {
  return n.toLocaleString('en-US');
}

export function DataSummaryTable({
  items,
  onDelete,
}: DataSummaryTableProps) {
  if (items.length === 0) {
    return (
      <p className="muted">
        No data yet. Load your first ticker via the form above.
      </p>
    );
  }

  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Timeframe</th>
            <th>Candles</th>
            <th>First Date</th>
            <th>Last Date</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr key={`${row.symbol}-${row.timeframe}`}>
              <td>{row.symbol}</td>
              <td>{row.timeframe}</td>
              <td>{fmtNumber(row.candles_count)}</td>
              <td>{fmtDate(row.first_timestamp)}</td>
              <td>{fmtDate(row.last_timestamp)}</td>
              <td>
                <button
                  type="button"
                  className="btn-delete-small"
                  onClick={() => onDelete(row.symbol, row.timeframe)}
                  title="Delete"
                >
                  ✕
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}