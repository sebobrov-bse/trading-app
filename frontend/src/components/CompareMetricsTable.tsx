import { useNavigate } from 'react-router-dom';
import type { BacktestForCompare } from '../api/types';

interface CompareMetricsTableProps {
  backtests: BacktestForCompare[];
}

interface MetricRow {
  key: string;
  label: string;
  format: (v: number) => string;
  higherIsBetter: boolean;
  get: (b: BacktestForCompare) => number;
}

function fmtSigned(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toLocaleString('en-US', {
    maximumFractionDigits: 2,
  })}`;
}

function fmtPct(v: number): string {
  return `${v.toFixed(2)}%`;
}

function fmtNum2(v: number): string {
  return v.toFixed(2);
}

function fmtInt(v: number): string {
  return String(Math.round(v));
}

const ROWS: MetricRow[] = [
  {
    key: 'pnl',
    label: 'PnL',
    format: fmtSigned,
    higherIsBetter: true,
    get: (b) => b.metrics.pnl,
  },
  {
    key: 'pnl_percent',
    label: 'PnL %',
    format: fmtPct,
    higherIsBetter: true,
    get: (b) => b.metrics.pnl_percent,
  },
  {
    key: 'cagr',
    label: 'CAGR',
    format: fmtPct,
    higherIsBetter: true,
    get: (b) => b.metrics.cagr,
  },
  {
    key: 'sharpe',
    label: 'Sharpe',
    format: fmtNum2,
    higherIsBetter: true,
    get: (b) => b.metrics.sharpe,
  },
  {
    key: 'sortino',
    label: 'Sortino',
    format: fmtNum2,
    higherIsBetter: true,
    get: (b) => b.metrics.sortino,
  },
  {
    key: 'calmar',
    label: 'Calmar',
    format: fmtNum2,
    higherIsBetter: true,
    get: (b) => b.metrics.calmar,
  },
  {
    key: 'max_drawdown',
    label: 'Max Drawdown',
    format: fmtPct,
    higherIsBetter: false, // smaller is better
    get: (b) => b.metrics.max_drawdown,
  },
  {
    key: 'win_rate',
    label: 'Win Rate',
    format: (v) => fmtPct(v * 100),
    higherIsBetter: true,
    get: (b) => b.metrics.win_rate,
  },
  {
    key: 'profit_factor',
    label: 'Profit Factor',
    format: fmtNum2,
    higherIsBetter: true,
    get: (b) => b.metrics.profit_factor,
  },
  {
    key: 'trades_count',
    label: 'Trades',
    format: fmtInt,
    higherIsBetter: true,
    get: (b) => b.metrics.trades_count,
  },
];

export function CompareMetricsTable({ backtests }: CompareMetricsTableProps) {
  const navigate = useNavigate();

  return (
    <div className="table-scroll">
      <table className="compare-table">
        <thead>
          <tr>
            <th>Metric</th>
            {backtests.map((b) => (
              <th
                key={b.id}
                onClick={() => navigate(`/history/${b.id}`)}
                className="clickable-header"
                title="Open details"
              >
                #{b.id} {b.strategy}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row) => {
            const values = backtests.map((b) => row.get(b));
            const best = row.higherIsBetter
              ? Math.max(...values)
              : Math.min(...values);
            const worst = row.higherIsBetter
              ? Math.min(...values)
              : Math.max(...values);

            return (
              <tr key={row.key}>
                <td className="metric-label-cell">{row.label}</td>
                {backtests.map((b, i) => {
                  const v = values[i];
                  const cls =
                    v === best && best !== worst
                      ? 'cell-best'
                      : v === worst && best !== worst
                        ? 'cell-worst'
                        : '';
                  return (
                    <td key={b.id} className={cls}>
                      {row.format(v)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}