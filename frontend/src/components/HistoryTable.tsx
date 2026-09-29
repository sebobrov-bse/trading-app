import type { BacktestHistoryItem } from '../api/types';

interface HistoryTableProps {
  items: BacktestHistoryItem[];
  onRowClick: (id: number) => void;
  onDelete: (id: number) => void;
}

function fmtMoney(v: number): string {
  return v.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

function fmtDate(s: string): string {
  return new Date(s).toLocaleString('en-GB', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function HistoryTable({
  items,
  onRowClick,
  onDelete,
}: HistoryTableProps) {
  if (items.length === 0) {
    return <p className="muted">No backtests found.</p>;
  }

  return (
    <div className="table-scroll">
      <table className="history-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Symbol</th>
            <th>TF</th>
            <th>Strategy</th>
            <th>PnL</th>
            <th>PnL %</th>
            <th>Sharpe</th>
            <th>Max DD</th>
            <th>Trades</th>
            <th>Created</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr
              key={row.id}
              onClick={() => onRowClick(row.id)}
              className="history-row"
            >
              <td>{row.id}</td>
              <td>{row.symbol}</td>
              <td>{row.timeframe}</td>
              <td>{row.strategy}</td>
              <td className={row.pnl >= 0 ? 'num-pos' : 'num-neg'}>
                {fmtMoney(row.pnl)}
              </td>
              <td className={row.pnl_percent >= 0 ? 'num-pos' : 'num-neg'}>
                {row.pnl_percent.toFixed(2)}%
              </td>
              <td>{row.sharpe.toFixed(3)}</td>
              <td>{row.max_drawdown.toFixed(2)}%</td>
              <td>{row.trades_count}</td>
              <td className="muted">{fmtDate(row.created_at)}</td>
              <td>
                <button
                  type="button"
                  className="btn-delete-small"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(row.id);
                  }}
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