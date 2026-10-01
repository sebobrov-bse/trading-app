import { useCallback, useEffect, useState } from 'react';
import { deleteData, getSummary } from '../api/data';
import type { DataSummaryResponse, LoadReport } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { DataLoadForm } from '../components/DataLoadForm';
import { DataSummaryTable } from '../components/DataSummaryTable';
import { LoadResultMessage } from '../components/LoadResultMessage';

export function Data() {
  const [summary, setSummary] = useState<DataSummaryResponse | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [lastReport, setLastReport] = useState<LoadReport | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{
    symbol: string;
    timeframe: number;
  } | null>(null);

  const refreshSummary = useCallback(async () => {
    setLoadingSummary(true);
    setError(null);
    try {
      const data = await getSummary();
      setSummary(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingSummary(false);
    }
  }, []);

  useEffect(() => {
    refreshSummary();
  }, [refreshSummary]);

  function handleLoaded(report: LoadReport) {
    setLastReport(report);
    refreshSummary();
  }

  async function handleDelete() {
    if (!pendingDelete) return;
    try {
      await deleteData(pendingDelete.symbol, pendingDelete.timeframe);
      setPendingDelete(null);
      await refreshSummary();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setPendingDelete(null);
    }
  }

  return (
    <div className="page">
      <h1>Data Manager</h1>

      <DataLoadForm onLoaded={handleLoaded} />

      {lastReport && (
        <LoadResultMessage
          report={lastReport}
          onDismiss={() => setLastReport(null)}
        />
      )}

      <h2>Loaded Data</h2>
      {loadingSummary && <p className="muted">Loading...</p>}
      {error && <div className="error-box">{error}</div>}
      {summary && (
        <DataSummaryTable
          items={summary.items}
          onDelete={(s, t) => setPendingDelete({ symbol: s, timeframe: t })}
        />
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete data?"
        message={
          pendingDelete
            ? `Delete all candles for ${pendingDelete.symbol} (tf=${pendingDelete.timeframe})? This cannot be undone.`
            : ''
        }
        confirmLabel="Delete"
        onConfirm={handleDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}