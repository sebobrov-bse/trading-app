import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { deleteBacktest, getBacktestHistory } from '../api/backtest';
import type { BacktestHistoryItem } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { HistoryFilters } from '../components/HistoryFilters';
import { HistoryTable } from '../components/HistoryTable';
import { Pagination } from '../components/Pagination';

export function History() {
  const navigate = useNavigate();
  const [symbol, setSymbol] = useState('');
  const [strategy, setStrategy] = useState('');
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<BacktestHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getBacktestHistory({
        symbol: symbol || undefined,
        strategy: strategy || undefined,
        limit,
        offset,
      });
      setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [symbol, strategy, limit, offset]);

  useEffect(() => {
    setOffset(0);
  }, [symbol, strategy, limit]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleDelete(id: number) {
    try {
      await deleteBacktest(id);
      setPendingDeleteId(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="page">
      <h1>Backtest History</h1>
      <HistoryFilters
        symbol={symbol}
        strategy={strategy}
        limit={limit}
        onSymbolChange={setSymbol}
        onStrategyChange={setStrategy}
        onLimitChange={setLimit}
      />
      {error && <div className="error-box">{error}</div>}
      {loading ? (
        <p className="muted">Loading...</p>
      ) : (
        <>
          <HistoryTable
            items={items}
            onRowClick={(id) => navigate(`/history/${id}`)}
            onDelete={(id) => setPendingDeleteId(id)}
          />
          <Pagination
            total={total}
            limit={limit}
            offset={offset}
            onOffsetChange={setOffset}
          />
        </>
      )}
      <ConfirmDialog
        open={pendingDeleteId !== null}
        title="Delete backtest?"
        message={`Backtest #${pendingDeleteId} will be permanently deleted.`}
        confirmLabel="Delete"
        onConfirm={() => pendingDeleteId && handleDelete(pendingDeleteId)}
        onCancel={() => setPendingDeleteId(null)}
      />
    </div>
  );
}