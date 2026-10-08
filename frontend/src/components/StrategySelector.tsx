import type { StrategyMetadata } from '../api/types';

interface StrategySelectorProps {
  strategies: StrategyMetadata[];
  selectedName: string | null;
  onSelect: (name: string) => void;
}

export function StrategySelector({
  strategies,
  selectedName,
  onSelect,
}: StrategySelectorProps) {
  const builtin = strategies.filter((s) => s.source === 'builtin');
  const custom = strategies.filter((s) => s.source === 'custom');
  const python = strategies.filter((s) => s.source === 'python');

  const selected = strategies.find((s) => s.name === selectedName) ?? null;

  return (
    <div className="strategy-selector">
      <label className="field">
        <span className="field-label">Стратегия</span>
        <select
          value={selectedName ?? ''}
          onChange={(e) => onSelect(e.target.value)}
        >
          <option value="" disabled>
            — выбери стратегию —
          </option>
          {python.length > 0 && (
            <optgroup label="Python-классы">
              {python.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.display_name}
                </option>
              ))}
            </optgroup>
          )}
          {builtin.length > 0 && (
            <optgroup label="Встроенные (DSL)">
              {builtin.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.display_name}
                </option>
              ))}
            </optgroup>
          )}
          {custom.length > 0 && (
            <optgroup label="Мои стратегии">
              {custom.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.display_name}
                </option>
              ))}
            </optgroup>
          )}
        </select>
      </label>

      {selected && (
        <div className="strategy-card-mini">
          <div className="strategy-card-mini-header">
            <strong>{selected.display_name}</strong>
            <span className={`source-badge source-${selected.source}`}>
              {selected.source}
            </span>
          </div>
          {selected.description && (
            <p className="strategy-card-mini-desc">{selected.description}</p>
          )}
          <div className="strategy-card-mini-meta">
            {selected.direction.long && <span>Long</span>}
            {selected.direction.short && <span>Short</span>}
            {selected.intraday_only && <span>Intraday</span>}
            {selected.tags.map((t) => (
              <span key={t} className="tag">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}