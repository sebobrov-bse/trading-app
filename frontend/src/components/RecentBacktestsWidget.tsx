import { useNavigate } from 'react-router-dom';
import type { BacktestHistoryItem } from '../api/types';

interface RecentBacktestsWidgetProps {
  items: BacktestHistoryItem[];
}

function fmtMoney(v: number): string {
  return v.toLocaleString('en-US', { maximumFractionDigits: 0 });
}

function fmtDate(s: string): string {
  return s.slice(0, 10);
}

export function RecentBacktestsWidget({ items }: RecentBacktestsWidgetProps) {
  const navigate = useNavigate();

  if (items.length === 0) {
    return (
      <p className="muted">
        No backtests yet. Run your first on the Backtest page.
      </p>
    );
  }

  return (
    <table className="compact-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Symbol</th>
          <th>Strategy</th>
          <th>PnL</th>
          <th>Sharpe</th>
          <th>Date</th>
        </tr>
      </thead>
      <tbody>
        {items.map((b) => (
          <tr
            key={b.id}
            onClick={() => navigate(`/history/${b.id}`)}
            className="clickable-row"
          >
            <td>{b.id}</td>
            <td>{b.symbol}</td>
            <td>{b.strategy}</td>
            <td className={b.pnl >= 0 ? 'num-pos' : 'num-neg'}>
              {fmtMoney(b.pnl)}
            </td>
            <td>{b.sharpe.toFixed(2)}</td>
            <td className="muted">{fmtDate(b.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
