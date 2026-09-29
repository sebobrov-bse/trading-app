import { useState } from 'react';
import { ApiError } from '../api/client';
import { runBacktest } from '../api/backtest';
import type { BacktestRequest, BacktestResult } from '../api/types';
import { Field } from './Field';

interface BacktestFormProps {
  onSuccess: (result: BacktestResult) => void;
}

interface FormState {
  symbol: string;
  timeframe: number;
  start: string;
  end: string;
  fast: number;
  slow: number;
  cash: number;
  commission: number;
}

type FormErrors = Partial<Record<keyof FormState, string>>;

const DEFAULTS: FormState = {
  symbol: 'SBER',
  timeframe: 24,
  start: '2024-01-01',
  end: new Date().toISOString().slice(0, 10),
  fast: 10,
  slow: 30,
  cash: 100000,
  commission: 0.001,
};

function validate(state: FormState): FormErrors {
  const errors: FormErrors = {};

  if (!/^[A-Z][A-Z0-9]{1,19}$/.test(state.symbol)) {
    errors.symbol = '2–20 chars, uppercase letters and digits only';
  }
  if (![1, 10, 60, 24].includes(state.timeframe)) {
    errors.timeframe = 'Must be 1, 10, 60, or 24';
  }
  if (!state.start || !state.end) {
    errors.start = 'Start and end are required';
  } else if (state.start > state.end) {
    errors.end = 'End must be after start';
  }
  if (state.fast < 2) errors.fast = 'Must be ≥ 2';
  if (state.slow < 3) errors.slow = 'Must be ≥ 3';
  if (state.fast >= state.slow) errors.slow = 'Slow must be > fast';
  if (state.cash <= 0) errors.cash = 'Must be > 0';
  if (state.commission < 0 || state.commission > 0.1) {
    errors.commission = 'Must be between 0 and 0.1';
  }

  return errors;
}

export function BacktestForm({ onSuccess }: BacktestFormProps) {
  const [form, setForm] = useState<FormState>(DEFAULTS);
  const [errors, setErrors] = useState<FormErrors>({});
  const [loading, setLoading] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setServerError(null);

    const validationErrors = validate(form);
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) {
      return;
    }

    setLoading(true);
    const request: BacktestRequest = {
      symbol: form.symbol,
      timeframe: form.timeframe,
      start: form.start,
      end: form.end,
      strategy: 'sma_crossover',
      params: { fast: form.fast, slow: form.slow },
      cash: form.cash,
      commission: form.commission,
    };

    try {
      const result = await runBacktest(request);
      onSuccess(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setServerError(`[${err.status}] ${err.detail}`);
      } else if (err instanceof TypeError) {
        setServerError('Backend unavailable. Is FastAPI running on :8000?');
      } else {
        setServerError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="backtest-form" onSubmit={handleSubmit} noValidate>
      <div className="form-grid">
        <Field label="Symbol" error={errors.symbol}>
          <input
            value={form.symbol}
            onChange={(e) => update('symbol', e.target.value.toUpperCase())}
          />
        </Field>

        <Field label="Timeframe" error={errors.timeframe}>
          <select
            value={form.timeframe}
            onChange={(e) => update('timeframe', Number(e.target.value))}
          >
            <option value={1}>1 min</option>
            <option value={10}>10 min</option>
            <option value={60}>1 hour</option>
            <option value={24}>1 day</option>
          </select>
        </Field>

        <Field label="Start" error={errors.start}>
          <input
            type="date"
            value={form.start}
            onChange={(e) => update('start', e.target.value)}
          />
        </Field>

        <Field label="End" error={errors.end}>
          <input
            type="date"
            value={form.end}
            onChange={(e) => update('end', e.target.value)}
          />
        </Field>

        <Field label="Fast SMA" error={errors.fast}>
          <input
            type="number"
            value={form.fast}
            onChange={(e) => update('fast', Number(e.target.value))}
          />
        </Field>

        <Field label="Slow SMA" error={errors.slow}>
          <input
            type="number"
            value={form.slow}
            onChange={(e) => update('slow', Number(e.target.value))}
          />
        </Field>

        <Field label="Cash" error={errors.cash}>
          <input
            type="number"
            value={form.cash}
            onChange={(e) => update('cash', Number(e.target.value))}
          />
        </Field>

        <Field label="Commission" error={errors.commission}>
          <input
            type="number"
            step="0.0001"
            value={form.commission}
            onChange={(e) => update('commission', Number(e.target.value))}
          />
        </Field>
      </div>

      {serverError && <div className="error-box">{serverError}</div>}

      <button type="submit" disabled={loading}>
        {loading ? 'Running...' : 'Run Backtest'}
      </button>
    </form>
  );
}