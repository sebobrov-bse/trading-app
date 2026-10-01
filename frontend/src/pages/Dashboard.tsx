import { useCallback, useEffect, useState } from 'react';
import { getBacktestHistory, getTopStrategies } from '../api/backtest';
import { getSummary } from '../api/data';
import { getHealth } from '../api/health';
import type {
  BacktestHistoryItem,
  DataSummaryResponse,
  TopStrategyItem,
} from '../api/types';
import { BackendStatus } from '../components/BackendStatus';
import { DataSummaryWidget } from '../components/DataSummaryWidget';
import { QuickActions } from '../components/QuickActions';
import { RecentBacktestsWidget } from '../components/RecentBacktestsWidget';
import { TopStrategiesWidget } from '../components/TopStrategiesWidget';
import { WidgetCard } from '../components/WidgetCard';

type HealthState = 'loading' | 'ok' | 'error';

export function Dashboard() {
  const [healthState, setHealthState] = useState<HealthState>('loading');
  const [database, setDatabase] = useState<string>('');
  const [healthError, setHealthError] = useState<string>('');
  const [summary, setSummary] = useState<DataSummaryResponse | null>(null);
  const [recent, setRecent] = useState<BacktestHistoryItem[]>([]);
  const [topStrategies, setTopStrategies] = useState<TopStrategyItem[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setHealthState('loading');

    const results = await Promise.allSettled([
      getHealth(),
      getSummary(),
      getBacktestHistory({ limit: 5 }),
      getTopStrategies(3),
    ]);

    const healthResult = results[0];
    if (healthResult.status === 'fulfilled') {
      setHealthState('ok');
      setDatabase(healthResult.value.database);
      setHealthError('');
    } else {
      setHealthState('error');
      setHealthError(String(healthResult.reason));
    }

    const summaryResult = results[1];
    if (summaryResult.status === 'fulfilled') {
      setSummary(summaryResult.value);
    } else {
      setSummary(null);
    }

    const recentResult = results[2];
    if (recentResult.status === 'fulfilled') {
      setRecent(recentResult.value.items);
    } else {
      setRecent([]);
    }

    const topResult = results[3];
    if (topResult.status === 'fulfilled') {
      setTopStrategies(topResult.value);
    } else {
      setTopStrategies([]);
    }

    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="page">
      <div className="dashboard-header">
        <h1>Dashboard</h1>
        <div className="dashboard-header-right">
          <BackendStatus
            status={healthState}
            database={database}
            errorMessage={healthError}
          />
          <button
            type="button"
            onClick={refresh}
            disabled={loading}
            className="btn-secondary"
          >
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      <QuickActions />

      <div className="widgets-grid">
        <WidgetCard title="Data Summary" actionLabel="Manage" actionTo="/data">
          <DataSummaryWidget summary={summary} />
        </WidgetCard>

        <WidgetCard
          title="Recent Backtests"
          actionLabel="All history"
          actionTo="/history"
        >
          <RecentBacktestsWidget items={recent} />
        </WidgetCard>

        <WidgetCard title="Top Strategies">
          <TopStrategiesWidget items={topStrategies} />
        </WidgetCard>
      </div>
    </div>
  );
}