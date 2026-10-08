import type { RiskConfigPreview } from '../api/types';

interface AppliedRiskConfigCardProps {
  config: RiskConfigPreview;
}

export function AppliedRiskConfigCard({ config }: AppliedRiskConfigCardProps) {
  if (!config.use_risk_management) {
    return (
      <div className="applied-risk-card applied-risk-disabled">
        <h4>Применённый риск-менеджмент</h4>
        <p>
          <strong>Риск-менеджмент отключён.</strong> Сделки без стопов и тейков.
        </p>
      </div>
    );
  }

  const rows: Array<[string, string | number]> = [
    ['Stop type', config.stop_type],
    ['ATR multiplier', config.atr_multiplier],
    ['Take profit R:R', config.take_profit_rr],
    ['Risk per trade %', config.risk_per_trade_pct],
    ['Max positions', config.max_positions ?? 3],
  ];

  return (
    <div className="applied-risk-card">
      <h4>Применённый риск-менеджмент</h4>
      <table className="applied-risk-table">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}>
              <td className="muted">{k}</td>
              <td>
                <strong>{String(v)}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}