import type { BacktestResult } from '../api/types';
import { MetricCard } from './MetricCard';

interface MetricsGridProps {
  result: BacktestResult;
}

function money(v: number): string {
  return v.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

function pct(v: number): string {
  return `${v.toFixed(2)}%`;
}

function num(v: number, digits = 3): string {
  return v.toFixed(digits);
}

export function MetricsGrid({ result }: MetricsGridProps) {
  const pnlVariant = result.pnl >= 0 ? 'positive' : 'negative';
  const sharpeVariant =
    result.sharpe >= 1 ? 'positive' : result.sharpe < 0 ? 'negative' : 'default';
  const ddVariant = result.max_drawdown > 20 ? 'negative' : 'default';
  const winRateVariant = result.win_rate >= 0.5 ? 'positive' : 'default';

  return (
    <div className="metrics-grid">
      <MetricCard
        label="Total PnL"
        value={money(result.pnl)}
        hint={pct(result.pnl_percent)}
        variant={pnlVariant}
      />
      <MetricCard
        label="Final Value"
        value={money(result.final_value)}
        variant={pnlVariant}
      />
      <MetricCard
        label="CAGR"
        value={pct(result.cagr)}
        variant={result.cagr >= 0 ? 'positive' : 'negative'}
      />
      <MetricCard
        label="Sharpe"
        value={num(result.sharpe)}
        hint="> 1 — good"
        variant={sharpeVariant}
      />
      <MetricCard label="Sortino" value={num(result.sortino)} />
      <MetricCard label="Calmar" value={num(result.calmar)} />
      <MetricCard
        label="Max Drawdown"
        value={pct(result.max_drawdown)}
        variant={ddVariant}
      />
      <MetricCard
        label="Win Rate"
        value={pct(result.win_rate * 100)}
        variant={winRateVariant}
      />
      <MetricCard label="Profit Factor" value={num(result.profit_factor, 2)} />
      <MetricCard label="Trades" value={String(result.trades)} />
      <MetricCard label="Bars" value={String(result.bars)} />
      <MetricCard
        label="Exposure"
        value={pct(result.exposure * 100)}
      />
    </div>
  );
}