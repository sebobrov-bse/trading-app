import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { deleteBacktest, getBacktest } from '../api/backtest';
import type { BacktestDetails } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { EquityChart } from '../components/EquityChart';
import { MetricsGrid } from '../components/MetricsGrid';
import { TradesTable } from '../components/TradesTable';

export function HistoryDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const backtestId = Number(id);

  const [data, setData] = useState<BacktestDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    if (!Number.isFinite(backtestId)) {
      setError('Invalid id');
      setLoading(false);
      return;
    }
    setLoading(true);
    getBacktest(backtestId)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [backtestId]);

  async function handleDelete() {
    try {
      await deleteBacktest(backtestId);
      navigate('/history');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setConfirmOpen(false);
    }
  }

  if (loading) {
    return <div className="page"><p className="muted">Loading...</p></div>;
  }

  if (error || !data) {
    return (
      <div className="page">
        <h1>Backtest not found</h1>
        <p className="error-box">{error ?? 'Not found'}</p>
        <Link to="/history" className="link">← Back to history</Link>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="detail-header">
        <div>
          <h1>Backtest #{data.id}</h1>
          <p className="muted">
            {data.symbol} · tf={data.timeframe} · {data.strategy} ·{' '}
            {data.start_date.slice(0, 10)} → {data.end_date.slice(0, 10)} ·{' '}
            {data.bars} bars
          </p>
        </div>
        <div className="detail-actions">
          <Link to="/history" className="btn-secondary">← Back</Link>
          <button
            type="button"
            className="btn-danger"
            onClick={() => setConfirmOpen(true)}
          >
            Delete
          </button>
        </div>
      </div>

      <MetricsGrid result={data} />

      <h3>Equity Curve</h3>
      <EquityChart data={data.equity_curve} />

      <h3>Trades ({data.trades_list.length})</h3>
      {data.trades_list.length > 200 && (
        <p className="muted">
          Showing all {data.trades_list.length} trades — consider filtering
          for very large datasets.
        </p>
      )}
      <TradesTable
        trades={data.trades_list}
        backtestId={data.id}
        limit={100000}
      />

      <ConfirmDialog
        open={confirmOpen}
        title="Delete backtest?"
        message={`Backtest #${data.id} will be permanently deleted.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}