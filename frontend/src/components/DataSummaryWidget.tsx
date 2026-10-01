import type { DataSummaryResponse } from '../api/types';

interface DataSummaryWidgetProps {
  summary: DataSummaryResponse | null;
}

export function DataSummaryWidget({ summary }: DataSummaryWidgetProps) {
  if (!summary || summary.items.length === 0) {
    return (
      <p className="muted">
        No data yet. Load your first ticker on the Data page.
      </p>
    );
  }

  const firstDates = summary.items.map((i) => i.first_timestamp).sort();
  const lastDates = summary.items.map((i) => i.last_timestamp).sort();
  const earliest = firstDates[0]?.slice(0, 10) ?? '—';
  const latest = lastDates[lastDates.length - 1]?.slice(0, 10) ?? '—';

  return (
    <div className="summary-stats">
      <div className="stat">
        <div className="stat-value">{summary.total_symbols}</div>
        <div className="stat-label">symbols</div>
      </div>
      <div className="stat">
        <div className="stat-value">
          {summary.total_candles.toLocaleString('en-US')}
        </div>
        <div className="stat-label">candles</div>
      </div>
      <div className="stat-wide">
        <div className="stat-label">Range</div>
        <div className="stat-value-small">
          {earliest} → {latest}
        </div>
      </div>
    </div>
  );
}