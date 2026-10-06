import { useCallback, useEffect, useState } from 'react';
import { compareBacktests, getBacktestHistory } from '../api/backtest';
import type { BacktestHistoryItem, CompareResponse } from '../api/types';
import { BacktestSelector } from '../components/BacktestSelector';
import { CompareEquityChart } from '../components/CompareEquityChart';
import { CompareMetricsTable } from '../components/CompareMetricsTable';
import { PeriodWarning } from '../components/PeriodWarning';

export function Compare() {
  const [available, setAvailable] = useState<BacktestHistoryItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [compareData, setCompareData] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAvailable = useCallback(async () => {
    try {
      const data = await getBacktestHistory({ limit: 100 });
      setAvailable(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    loadAvailable();
  }, [loadAvailable]);

  function toggleSelection(id: number) {
    setSelectedIds((prev) => {
      if (prev.includes(id)) {
        return prev.filter((x) => x !== id);
      }
      if (prev.length >= 5) {
        return prev; // limit reached
      }
      return [...prev, id];
    });
  }

  async function handleCompare() {
    if (selectedIds.length < 2) return;
    setLoading(true);
    setError(null);
    try {
      const data = await compareBacktests(selectedIds);
      setCompareData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setCompareData(null);
    } finally {
      setLoading(false);
    }
  }

  const canCompare = selectedIds.length >= 2 && selectedIds.length <= 5;

  return (
    <div className="page">
      <h1>Compare Backtests</h1>

      <div className="compare-layout">
        <div className="compare-sidebar">
          <BacktestSelector
            items={available}
            selectedIds={selectedIds}
            onToggle={toggleSelection}
          />
          <button
            type="button"
            className="btn-primary"
            disabled={!canCompare || loading}
            onClick={handleCompare}
            title={
              canCompare
                ? 'Compare selected'
                : 'Select 2-5 backtests to compare'
            }
          >
            {loading ? 'Comparing...' : `Compare (${selectedIds.length})`}
          </button>
        </div>

        <div className="compare-content">
          {error && <div className="error-box">{error}</div>}

          {!compareData && !loading && !error && (
            <p className="muted">
              Select 2-5 backtests on the left and click Compare.
            </p>
          )}

          {compareData && (
            <>
              <PeriodWarning
                backtests={compareData.backtests}
                commonPeriod={compareData.common_period}
              />
              <CompareMetricsTable backtests={compareData.backtests} />
              <h3>Equity Curves</h3>
              <CompareEquityChart backtests={compareData.backtests} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}