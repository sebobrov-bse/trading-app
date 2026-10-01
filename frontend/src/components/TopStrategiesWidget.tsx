import { useNavigate } from 'react-router-dom';
import type { TopStrategyItem } from '../api/types';

interface TopStrategiesWidgetProps {
  items: TopStrategyItem[];
}

function fmtMoney(v: number): string {
  return v.toLocaleString('en-US', { maximumFractionDigits: 0 });
}

export function TopStrategiesWidget({ items }: TopStrategiesWidgetProps) {
  const navigate = useNavigate();

  if (items.length === 0) {
    return <p className="muted">Not enough data for analysis yet.</p>;
  }

  return (
    <div className="top-strategies">
      {items.map((s) => (
        <div
          key={s.strategy}
          className="strategy-card"
          onClick={() => navigate(`/history?strategy=${s.strategy}`)}
        >
          <div className="strategy-name">{s.strategy}</div>
          <div className="strategy-sharpe">{s.avg_sharpe.toFixed(2)}</div>
          <div className="strategy-meta">
            avg PnL: {fmtMoney(s.avg_pnl)} · {s.count} runs
          </div>
        </div>
      ))}
    </div>
  );
}