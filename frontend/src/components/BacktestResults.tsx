import { Link } from 'react-router-dom';
import type { BacktestResult } from '../api/types';
import { MetricsGrid } from './MetricsGrid';
import { TradesTable } from './TradesTable';

interface BacktestResultsProps {
  result: BacktestResult;
}

export function BacktestResults({ result }: BacktestResultsProps) {
  const equity = result.equity_curve;
  const equitySummary =
    equity.length > 0
      ? `${equity.length} points, from ${equity[0].value.toFixed(0)} to ${equity[equity.length - 1].value.toFixed(0)}`
      : 'no data';

  return (
    <div className="backtest-result">
      <div className="result-header">
        <h2>
          Result <span className="muted">#{result.id ?? '—'}</span>
        </h2>
        {result.id && (
          <Link to={`/history/${result.id}`} className="link">
            Full details →
          </Link>
        )}
      </div>

      <p className="muted">
        {result.symbol} · tf={result.timeframe} · {result.strategy} ·{' '}
        {result.start} → {result.end} · {result.bars} bars
      </p>

      <MetricsGrid result={result} />

      <h3>Equity Curve</h3>
      <p className="muted">{equitySummary}</p>

      <h3>Trades ({result.trades_list.length})</h3>
      <TradesTable trades={result.trades_list} backtestId={result.id} />
    </div>
  );
}