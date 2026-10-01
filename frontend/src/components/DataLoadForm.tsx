import { useState } from 'react';
import { ApiError } from '../api/client';
import { loadHistory } from '../api/data';
import type { LoadReport, LoadRequest } from '../api/types';
import { Field } from './Field';

interface DataLoadFormProps {
  onLoaded: (report: LoadReport) => void;
}

interface FormState {
  symbol: string;
  timeframe: number;
  start: string;
  end: string;
}

type FormErrors = Partial<Record<keyof FormState, string>>;

const DEFAULTS: FormState = {
  symbol: 'SBER',
  timeframe: 24,
  start: '2023-01-01',
  end: '2024-12-31',
};

function validate(state: FormState): FormErrors {
  const errors: FormErrors = {};
  if (!/^[A-Z][A-Z0-9]{1,19}$/.test(state.symbol)) {
    errors.symbol = '2-20 chars, uppercase letters and digits only';
  }
  if (![1, 10, 60, 24].includes(state.timeframe)) {
    errors.timeframe = 'Must be 1, 10, 60, or 24';
  }
  if (!state.start || !state.end) {
    errors.start = 'Start and end are required';
  } else if (state.start > state.end) {
    errors.end = 'End must be after start';
  }
  return errors;
}

export function DataLoadForm({ onLoaded }: DataLoadFormProps) {
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
    if (Object.keys(validationErrors).length > 0) return;

    setLoading(true);
    const request: LoadRequest = {
      symbol: form.symbol,
      timeframe: form.timeframe,
      start: form.start,
      end: form.end,
    };

    try {
      const report = await loadHistory(request);
      onLoaded(report);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        setServerError(
          'Loading took more than 60 seconds. Check backend logs - data may still have loaded. Refresh the summary.',
        );
      } else if (err instanceof ApiError) {
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
      </div>

      {serverError && <div className="error-box">{serverError}</div>}

      <button type="submit" disabled={loading}>
        {loading
          ? `Loading ${form.symbol} ${form.timeframe}... up to 60s`
          : 'Load History'}
      </button>
    </form>
  );
}