import type { RiskConfigPreview } from '../api/types';
import { Field } from './Field';

interface RiskConfigSectionProps {
  value: RiskConfigPreview;
  overridden: boolean;
  onOverrideChange: (overridden: boolean) => void;
  onChange: (patch: Partial<RiskConfigPreview>) => void;
}

export function RiskConfigSection({
  value,
  overridden,
  onOverrideChange,
  onChange,
}: RiskConfigSectionProps) {
  const disabled = !overridden;

  return (
    <div className="risk-section">
      <div className="risk-section-header">
        <h3>Risk Management</h3>
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={overridden}
            onChange={(e) => onOverrideChange(e.target.checked)}
          />
          <span>Переопределить дефолт</span>
        </label>
      </div>

      {disabled && (
        <p className="muted">
          Используется default_risk_config стратегии. Поставь галку, чтобы изменить.
        </p>
      )}

      <div className="form-grid">
        <Field label="Use Risk Management">
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={value.use_risk_management}
              disabled={disabled}
              onChange={(e) =>
                onChange({ use_risk_management: e.target.checked })
              }
            />
            <span>Включён</span>
          </label>
        </Field>

        <Field label="Stop Type">
          <select
            value={value.stop_type}
            disabled={disabled}
            onChange={(e) =>
              onChange({
                stop_type: e.target.value as RiskConfigPreview['stop_type'],
              })
            }
          >
            <option value="atr">ATR</option>
            <option value="percent">Percent</option>
            <option value="n_bars">N bars</option>
          </select>
        </Field>

        <Field label="ATR Multiplier">
          <input
            type="number"
            step="0.1"
            min="0.5"
            max="5"
            value={value.atr_multiplier}
            disabled={disabled}
            onChange={(e) =>
              onChange({ atr_multiplier: Number(e.target.value) })
            }
          />
        </Field>

        <Field label="Take Profit R:R">
          <input
            type="number"
            step="0.5"
            min="1"
            max="10"
            value={value.take_profit_rr}
            disabled={disabled}
            onChange={(e) =>
              onChange({ take_profit_rr: Number(e.target.value) })
            }
          />
        </Field>

        <Field label="Risk per Trade %">
          <input
            type="number"
            step="0.1"
            min="0.1"
            max="5"
            value={value.risk_per_trade_pct}
            disabled={disabled}
            onChange={(e) =>
              onChange({ risk_per_trade_pct: Number(e.target.value) })
            }
          />
        </Field>

        <Field label="Max Positions">
          <input
            type="number"
            step="1"
            min="1"
            max="10"
            value={value.max_positions ?? 3}
            disabled={disabled}
            onChange={(e) =>
              onChange({ max_positions: Number(e.target.value) })
            }
          />
        </Field>

        {value.stop_type === 'percent' && (
          <Field label="Stop Percent %">
            <input
              type="number"
              step="0.1"
              min="0.1"
              max="10"
              value={value.stop_percent ?? 2.0}
              disabled={disabled}
              onChange={(e) =>
                onChange({ stop_percent: Number(e.target.value) })
              }
            />
          </Field>
        )}
      </div>
    </div>
  );
}