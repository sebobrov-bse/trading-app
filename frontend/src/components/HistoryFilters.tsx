interface HistoryFiltersProps {
  symbol: string;
  strategy: string;
  limit: number;
  onSymbolChange: (v: string) => void;
  onStrategyChange: (v: string) => void;
  onLimitChange: (v: number) => void;
}

export function HistoryFilters({
  symbol,
  strategy,
  limit,
  onSymbolChange,
  onStrategyChange,
  onLimitChange,
}: HistoryFiltersProps) {
  return (
    <div className="history-filters">
      <label className="filter-field">
        <span>Symbol</span>
        <input
          value={symbol}
          placeholder="SBER"
          onChange={(e) => onSymbolChange(e.target.value.toUpperCase())}
        />
      </label>

      <label className="filter-field">
        <span>Strategy</span>
        <input
          value={strategy}
          placeholder="sma_crossover"
          onChange={(e) => onStrategyChange(e.target.value)}
        />
      </label>

      <label className="filter-field">
        <span>Limit</span>
        <select
          value={limit}
          onChange={(e) => onLimitChange(Number(e.target.value))}
        >
          <option value={10}>10</option>
          <option value={25}>25</option>
          <option value={50}>50</option>
          <option value={100}>100</option>
        </select>
      </label>
    </div>
  );
}