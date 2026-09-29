import { Link } from 'react-router-dom';
import type { TradeInfo } from '../api/types';

interface TradesTableProps {
  trades: TradeInfo[];
  backtestId: number | null;
  limit?: number;
}

export function TradesTable({
  trades,
  backtestId,
  limit = 50,
}: TradesTableProps) {
  if (trades.length === 0) {
    return <p className="muted">No trades.</p>;
  }

  const visible = trades.slice(0, limit);
  const hasMore = trades.length > limit;

  return (
    <>
      <div className="table-scroll">
        <table className="trades-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Entry</th>
              <th>Exit</th>
              <th>Entry Price</th>
              <th>Exit Price</th>
              <th>Size</th>
              <th>PnL Net</th>
              <th>PnL %</th>
              <th>Bars</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((t, i) => (
              <tr key={i}>
                <td>{i + 1}</td>
                <td>{t.entry_time.slice(0, 10)}</td>
                <td>{t.exit_time.slice(0, 10)}</td>
                <td>{t.entry_price.toFixed(2)}</td>
                <td>{t.exit_price.toFixed(2)}</td>
                <td>{t.size.toFixed(2)}</td>
                <td className={t.pnl_net >= 0 ? 'num-pos' : 'num-neg'}>
                  {t.pnl_net.toFixed(2)}
                </td>
                <td className={t.pnl_percent >= 0 ? 'num-pos' : 'num-neg'}>
                  {t.pnl_percent.toFixed(2)}%
                </td>
                <td>{t.bars_held}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {hasMore && (
        <p className="muted">
          Showing {limit} of {trades.length} trades.{' '}
          {backtestId && (
            <Link to={`/history/${backtestId}`}>Show all →</Link>
          )}
        </p>
      )}
    </>
  );
}