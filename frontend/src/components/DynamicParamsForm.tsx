import type { StrategyParamSpec } from '../api/types';
import { Field } from './Field';

export type ParamsValues = Record<string, number | boolean | string>;
export type ParamsErrors = Record<string, string>;

interface DynamicParamsFormProps {
  params: StrategyParamSpec[];
  values: ParamsValues;
  errors: ParamsErrors;
  onChange: (name: string, value: number | boolean | string) => void;
}

function validateParam(
  spec: StrategyParamSpec,
  value: number | boolean | string | undefined,
): string | null {
  if (value === undefined || value === null || value === '') {
    return 'Обязательное поле';
  }

  if (spec.type === 'int' || spec.type === 'float') {
    const num = typeof value === 'number' ? value : Number(value);
    if (Number.isNaN(num)) return 'Должно быть число';
    if (spec.type === 'int' && !Number.isInteger(num)) {
      return 'Должно быть целое число';
    }
    if (spec.min !== null && spec.min !== undefined && num < spec.min) {
      return `Минимум: ${spec.min}`;
    }
    if (spec.max !== null && spec.max !== undefined && num > spec.max) {
      return `Максимум: ${spec.max}`;
    }
  }

  return null;
}

export function validateParams(
  specs: StrategyParamSpec[],
  values: ParamsValues,
): ParamsErrors {
  const errors: ParamsErrors = {};
  for (const spec of specs) {
    const msg = validateParam(spec, values[spec.name]);
    if (msg) errors[spec.name] = msg;
  }
  return errors;
}

export function DynamicParamsForm({
  params,
  values,
  errors,
  onChange,
}: DynamicParamsFormProps) {
  if (params.length === 0) {
    return (
      <p className="muted">
        У этой стратегии нет настраиваемых параметров.
      </p>
    );
  }

  return (
    <div className="dynamic-params-form">
      <div className="form-grid">
        {params.map((p) => {
          const value = values[p.name] ?? p.default;
          const error = errors[p.name];

          if (p.type === 'bool') {
            return (
              <Field key={p.name} label={p.name} error={error}>
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={Boolean(value)}
                    onChange={(e) => onChange(p.name, e.target.checked)}
                  />
                  <span>{p.description || p.name}</span>
                </label>
              </Field>
            );
          }

          if (p.type === 'str') {
            return (
              <Field key={p.name} label={p.name} error={error}>
                <input
                  type="text"
                  value={String(value ?? '')}
                  onChange={(e) => onChange(p.name, e.target.value)}
                  title={p.description}
                />
              </Field>
            );
          }

          return (
            <Field key={p.name} label={p.name} error={error}>
              <input
                type="number"
                step={p.type === 'int' ? 1 : 0.01}
                min={p.min ?? undefined}
                max={p.max ?? undefined}
                value={Number(value)}
                onChange={(e) =>
                  onChange(
                    p.name,
                    e.target.value === '' ? '' : Number(e.target.value),
                  )
                }
                title={p.description}
              />
            </Field>
          );
        })}
      </div>
    </div>
  );
}