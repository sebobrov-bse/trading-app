import type { BacktestHistoryItem } from '../api/types';

interface BacktestSelectorProps {
  items: BacktestHistoryItem[];
  selectedIds: number[];
  onToggle: (id: number) => void;
  maxSelection?: number;
}

export function BacktestSelector({
  items,
  selectedIds,
  onToggle,
  maxSelection = 5,
}: BacktestSelectorProps) {
  const atLimit = selectedIds.length >= maxSelection;

  if (items.length === 0) {
    return (
      <p className="muted">
        No backtests available. Run a few on the Backtest page first.
      </p>
    );
  }

  return (
    <div className="selector">
      <div className="selector-counter">
        Selected: <strong>{selectedIds.length}</strong> of {maxSelection}
      </div>
      <ul className="selector-list">
        {items.map((b) => {
          const selected = selectedIds.includes(b.id);
          const disabled = !selected && atLimit;
          return (
            <li
              key={b.id}
              className={`selector-item ${selected ? 'selected' : ''} ${
                disabled ? 'disabled' : ''
              }`}
            >
              <label>
                <input
                  type="checkbox"
                  checked={selected}
                  disabled={disabled}
                  onChange={() => onToggle(b.id)}
                />
                <div className="selector-body">
                  <div className="selector-line">
                    <strong>#{b.id}</strong> {b.symbol} · {b.strategy}
                  </div>
                  <div className="selector-meta">
                    {b.created_at.slice(0, 10)} · PnL{' '}
                    <span className={b.pnl >= 0 ? 'num-pos' : 'num-neg'}>
                      {b.pnl.toFixed(0)}
                    </span>{' '}
                    · Sharpe {b.sharpe.toFixed(2)}
                  </div>
                </div>
              </label>
            </li>
          );
        })}
      </ul>
    </div>
  );
}