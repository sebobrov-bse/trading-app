import type { RiskConfigPreview } from '../api/types';
import { Field } from './Field';

interface AdvancedRiskSettingsProps {
  value: RiskConfigPreview;
  disabled: boolean;
  onChange: (patch: Partial<RiskConfigPreview>) => void;
}

export function AdvancedRiskSettings({
  value,
  disabled,
  onChange,
}: AdvancedRiskSettingsProps) {
  const numField = (
    label: string,
    key: keyof RiskConfigPreview,
    step: number,
    min?: number,
    max?: number,
  ) => (
    <Field key={key} label={label}>
      <input
        type="number"
        step={step}
        min={min}
        max={max}
        value={(value[key] as number | undefined) ?? ''}
        disabled={disabled}
        onChange={(e) =>
          onChange({
            [key]:
              e.target.value === '' ? undefined : Number(e.target.value),
          } as Partial<RiskConfigPreview>)
        }
      />
    </Field>
  );

  const boolField = (label: string, key: keyof RiskConfigPreview) => (
    <Field key={key} label={label}>
      <label className="checkbox-field">
        <input
          type="checkbox"
          checked={Boolean(value[key])}
          disabled={disabled}
          onChange={(e) =>
            onChange({
              [key]: e.target.checked,
            } as Partial<RiskConfigPreview>)
          }
        />
        <span>{label}</span>
      </label>
    </Field>
  );

  return (
    <details className="advanced-risk">
      <summary>Advanced Risk Settings</summary>
      <div className="form-grid">
        {numField('ATR Period', 'atr_period', 1, 2, 200)}
        {numField('Stop N Bars', 'stop_n_bars', 1, 2, 200)}
        {numField('Max Daily Loss %', 'max_daily_loss_pct', 0.1, 0.1, 50)}
        {numField('Max Weekly Loss %', 'max_weekly_loss_pct', 0.1, 0.1, 100)}
        {numField('Max Monthly Loss %', 'max_monthly_loss_pct', 0.1, 0.1, 100)}
        {numField('Move to BE after R', 'move_to_breakeven_after_rr', 0.5, 0, 10)}
        {numField('Trailing after R', 'trailing_after_rr', 0.5, 0, 20)}
        {numField('Trailing ATR mult', 'trailing_atr_multiplier', 0.1, 0.1, 10)}
        {numField('Min ATR / Stop ratio', 'min_atr_to_stop_ratio', 0.5, 0, 50)}
        {boolField('Check ATR', 'check_atr')}
        {boolField('Long only', 'long_only')}
        {boolField('Short only', 'short_only')}
        {boolField('Intraday only', 'intraday_only')}
      </div>
    </details>
  );
}