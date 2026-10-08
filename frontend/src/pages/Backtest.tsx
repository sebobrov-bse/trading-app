import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ApiError } from '../api/client';
import { getStrategies } from '../api/strategies';
import { runBacktest } from '../api/backtest';
import type {
  BacktestRequest,
  BacktestResult,
  RiskConfigPreview,
  StrategyMetadata,
} from '../api/types';
import { AdvancedRiskSettings } from '../components/AdvancedRiskSettings';
import { AppliedRiskConfigCard } from '../components/AppliedRiskConfigCard';
import { BacktestResults } from '../components/BacktestResults';
import {
  DynamicParamsForm,
  validateParams,
  type ParamsErrors,
  type ParamsValues,
} from '../components/DynamicParamsForm';
import { Field } from '../components/Field';
import { RiskConfigSection } from '../components/RiskConfigSection';
import { StrategyLoadError } from '../components/StrategyLoadError';
import { StrategySelector } from '../components/StrategySelector';

interface BasicFormState {
  symbol: string;
  timeframe: number;
  start: string;
  end: string;
  cash: number;
  commission: number;
}

const BASIC_DEFAULTS: BasicFormState = {
  symbol: 'SBER',
  timeframe: 24,
  start: '2024-01-01',
  end: new Date().toISOString().slice(0, 10),
  cash: 100000,
  commission: 0.001,
};

function buildParamsFromStrategy(strategy: StrategyMetadata): ParamsValues {
  const result: ParamsValues = {};
  for (const p of strategy.params) {
    result[p.name] = p.default;
  }
  return result;
}

function buildRiskFromStrategy(strategy: StrategyMetadata): RiskConfigPreview {
  return { ...strategy.default_risk_config };
}

export function Backtest() {
  const [searchParams, setSearchParams] = useSearchParams();

  const [strategies, setStrategies] = useState<StrategyMetadata[]>([]);
  const [loadingStrategies, setLoadingStrategies] = useState(false);
  const [strategiesError, setStrategiesError] = useState<string | null>(null);

  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [basic, setBasic] = useState<BasicFormState>(BASIC_DEFAULTS);
  const [params, setParams] = useState<ParamsValues>({});
  const [paramErrors, setParamErrors] = useState<ParamsErrors>({});

  const [riskConfig, setRiskConfig] = useState<RiskConfigPreview | null>(null);
  const [riskOverridden, setRiskOverridden] = useState(false);

  const [loadingBacktest, setLoadingBacktest] = useState(false);
  const [backtestError, setBacktestError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);

  const selectedStrategy =
    strategies.find((s) => s.name === selectedName) ?? null;

  // ---- Load strategies ----
  const loadStrategies = useCallback(async () => {
    setLoadingStrategies(true);
    setStrategiesError(null);
    try {
      const data = await getStrategies();
      setStrategies(data.items);
    } catch (err) {
      setStrategiesError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingStrategies(false);
    }
  }, []);

  useEffect(() => {
    loadStrategies();
  }, [loadStrategies]);

  // Apply URL params once after strategies are loaded.
  useEffect(() => {
    if (strategies.length === 0 || selectedName) return;

    const urlStrategy = searchParams.get('strategy') ?? 'sma_crossover';
    const found =
      strategies.find((s) => s.name === urlStrategy) ?? strategies[0];

    setSelectedName(found.name);
    setBasic({
      symbol: searchParams.get('symbol') ?? BASIC_DEFAULTS.symbol,
      timeframe: Number(
        searchParams.get('timeframe') ?? BASIC_DEFAULTS.timeframe,
      ),
      start: searchParams.get('start') ?? BASIC_DEFAULTS.start,
      end: searchParams.get('end') ?? BASIC_DEFAULTS.end,
      cash: Number(searchParams.get('cash') ?? BASIC_DEFAULTS.cash),
      commission: Number(
        searchParams.get('commission') ?? BASIC_DEFAULTS.commission,
      ),
    });
  }, [strategies, selectedName, searchParams]);

  // On strategy change: reset params + risk to defaults.
  useEffect(() => {
    if (!selectedStrategy) return;
    setParams(buildParamsFromStrategy(selectedStrategy));
    setRiskConfig(buildRiskFromStrategy(selectedStrategy));
    setParamErrors({});
    setResult(null);
    setRiskOverridden(false);
  }, [selectedName]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- Handlers ----
  function handleParamChange(
    name: string,
    value: number | boolean | string,
  ) {
    setParams((prev) => ({ ...prev, [name]: value }));
  }

  function handleRiskChange(patch: Partial<RiskConfigPreview>) {
    setRiskConfig((prev) => (prev ? { ...prev, ...patch } : null));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedStrategy) return;

    setBacktestError(null);
    setResult(null);

    const pErrors = validateParams(selectedStrategy.params, params);
    setParamErrors(pErrors);
    if (Object.keys(pErrors).length > 0) return;

    setLoadingBacktest(true);

    const request: BacktestRequest = {
      symbol: basic.symbol,
      timeframe: basic.timeframe,
      start: basic.start,
      end: basic.end,
      strategy: selectedStrategy.name,
      params,
      cash: basic.cash,
      commission: basic.commission,
      risk_config: riskOverridden ? riskConfig : null,
    };

    try {
      const data = await runBacktest(request);
      setResult(data);

      const sp = new URLSearchParams({
        strategy: selectedStrategy.name,
        symbol: basic.symbol,
        timeframe: String(basic.timeframe),
        start: basic.start,
        end: basic.end,
      });
      setSearchParams(sp, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setBacktestError(`[${err.status}] ${err.detail}`);
      } else if (err instanceof TypeError) {
        setBacktestError(
          'Backend unavailable. Is FastAPI running on :8000?',
        );
      } else {
        setBacktestError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setLoadingBacktest(false);
    }
  }

  // ---- Render ----
  if (strategiesError) {
    return (
      <div className="page">
        <h1>Backtest</h1>
        <StrategyLoadError
          message={strategiesError}
          onRetry={loadStrategies}
        />
      </div>
    );
  }

  if (loadingStrategies || !selectedStrategy) {
    return (
      <div className="page">
        <h1>Backtest</h1>
        <p className="muted">Loading strategies...</p>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>Backtest</h1>

      <form className="backtest-form" onSubmit={handleSubmit} noValidate>
        <StrategySelector
          strategies={strategies}
          selectedName={selectedName}
          onSelect={setSelectedName}
        />

        <h3>Basic</h3>
        <div className="form-grid">
          <Field label="Symbol">
            <input
              value={basic.symbol}
              onChange={(e) =>
                setBasic({
                  ...basic,
                  symbol: e.target.value.toUpperCase(),
                })
              }
            />
          </Field>
          <Field label="Timeframe">
            <select
              value={basic.timeframe}
              onChange={(e) =>
                setBasic({ ...basic, timeframe: Number(e.target.value) })
              }
            >
              <option value={1}>1 min</option>
              <option value={10}>10 min</option>
              <option value={60}>1 hour</option>
              <option value={24}>1 day</option>
            </select>
          </Field>
          <Field label="Start">
            <input
              type="date"
              value={basic.start}
              onChange={(e) =>
                setBasic({ ...basic, start: e.target.value })
              }
            />
          </Field>
          <Field label="End">
            <input
              type="date"
              value={basic.end}
              onChange={(e) => setBasic({ ...basic, end: e.target.value })}
            />
          </Field>
          <Field label="Cash">
            <input
              type="number"
              value={basic.cash}
              onChange={(e) =>
                setBasic({ ...basic, cash: Number(e.target.value) })
              }
            />
          </Field>
          <Field label="Commission">
            <input
              type="number"
              step="0.0001"
              value={basic.commission}
              onChange={(e) =>
                setBasic({
                  ...basic,
                  commission: Number(e.target.value),
                })
              }
            />
          </Field>
        </div>

        <h3>Strategy Params</h3>
        <DynamicParamsForm
          params={selectedStrategy.params}
          values={params}
          errors={paramErrors}
          onChange={handleParamChange}
        />

        <h3>Risk Management</h3>
        {riskConfig && (
          <>
            <RiskConfigSection
              value={riskConfig}
              overridden={riskOverridden}
              onOverrideChange={setRiskOverridden}
              onChange={handleRiskChange}
            />
            <AdvancedRiskSettings
              value={riskConfig}
              disabled={!riskOverridden}
              onChange={handleRiskChange}
            />
          </>
        )}

        {backtestError && <div className="error-box">{backtestError}</div>}

        <button type="submit" disabled={loadingBacktest}>
          {loadingBacktest ? 'Running...' : 'Run Backtest'}
        </button>
      </form>

      {result && (
        <div className="backtest-result">
          {result.applied_risk_config && (
            <AppliedRiskConfigCard config={result.applied_risk_config} />
          )}
          <BacktestResults result={result} />
        </div>
      )}
    </div>
  );
}