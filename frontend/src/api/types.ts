export interface HealthResponse {
  status: string;
  database: string;
}

export interface Candle {
  id: number;
  symbol: string;
  timeframe: number;
  timestamp: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: number;
  value: string | null;
  created_at: string;
}

export interface CandleListResponse {
  items: Candle[];
  total: number;
  limit: number;
  offset: number;
}

export interface BacktestRequest {
  symbol: string;
  timeframe: number;
  start: string;
  end: string;
  strategy: string;
  params: Record<string, unknown>;
  cash?: number;
  commission?: number;
  risk_config?: RiskConfigPreview | null;
}

export interface TradeInfo {
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  size: number;
  bars_held: number;
  pnl: number;
  pnl_net: number;
  pnl_percent: number;
}

export interface EquityPoint {
  timestamp: string;
  value: number;
}

export interface BacktestResult {
  id: number | null;
  symbol: string;
  timeframe: number;
  start: string;
  end: string;
  strategy: string;
  params: Record<string, unknown>;
  bars: number;
  trades: number;
  final_value: number;
  pnl: number;
  pnl_percent: number;
  cagr: number;
  max_drawdown: number;
  sharpe: number;
  sortino: number;
  calmar: number;
  win_rate: number;
  profit_factor: number;
  avg_win: number;
  avg_loss: number;
  exposure: number;
  equity_curve: EquityPoint[];
  trades_list: TradeInfo[];
  applied_risk_config?: RiskConfigPreview | null;
}

export interface BacktestHistoryItem {
  id: number;
  symbol: string;
  timeframe: number;
  strategy: string;
  pnl: number;
  pnl_percent: number;
  sharpe: number;
  max_drawdown: number;
  trades_count: number;
  created_at: string;
}

export interface BacktestHistoryResponse {
  items: BacktestHistoryItem[];
  total: number;
  limit: number;
  offset: number;
}
export interface BacktestDetails {
  id: number;
  symbol: string;
  timeframe: number;
  start_date: string;
  end_date: string;
  strategy: string;
  params: Record<string, unknown>;
  cash: number;
  commission: number;
  bars: number;
  trades_count: number;
  final_value: number;
  pnl: number;
  pnl_percent: number;
  cagr: number;
  sharpe: number;
  sortino: number;
  calmar: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  avg_win: number;
  avg_loss: number;
  exposure: number;
  created_at: string;
  trades_list: TradeInfo[];
  equity_curve: EquityPoint[];
}
export interface LoadRequest {
  symbol: string;
  timeframe: number;
  start: string;
  end: string;
}

export interface LoadReport {
  symbol: string;
  timeframe: number;
  start: string;
  end: string;
  fetched: number;
  inserted: number;
  duplicates_skipped: number;
  duration_seconds: number;
}

export interface DataSummaryItem {
  symbol: string;
  timeframe: number;
  candles_count: number;
  first_timestamp: string;
  last_timestamp: string;
}

export interface DataSummaryResponse {
  items: DataSummaryItem[];
  total_symbols: number;
  total_candles: number;
}

export interface DeleteResponse {
  symbol: string;
  timeframe: number;
  deleted: number;
}

export interface TopStrategyItem {
  strategy: string;
  count: number;
  avg_sharpe: number;
  avg_pnl: number;
  avg_max_drawdown: number;
}

export interface BacktestMetrics {
  pnl: number;
  pnl_percent: number;
  cagr: number;
  sharpe: number;
  sortino: number;
  calmar: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  trades_count: number;
}

export interface BacktestForCompare {
  id: number;
  symbol: string;
  timeframe: number;
  start: string;
  end: string;
  strategy: string;
  params: Record<string, unknown>;
  metrics: BacktestMetrics;
  equity_curve: EquityPoint[];
}

export interface CommonPeriod {
  start: string;
  end: string;
}

export interface CompareResponse {
  backtests: BacktestForCompare[];
  common_period: CommonPeriod;
}

// ---- Strategy metadata (B.1 / B.2) ----

export interface StrategyParamSpec {
  name: string;
  type: 'int' | 'float' | 'bool' | 'str';
  default: number | boolean | string;
  min?: number | null;
  max?: number | null;
  description: string;
}

export interface RiskConfigPreview {
  use_risk_management: boolean;
  stop_type: 'atr' | 'percent' | 'n_bars';
  atr_multiplier: number;
  take_profit_rr: number;
  risk_per_trade_pct: number;

  // Optional advanced fields (present when overridden)
  atr_period?: number;
  stop_percent?: number;
  stop_n_bars?: number;
  max_positions?: number;
  max_daily_loss_pct?: number;
  max_weekly_loss_pct?: number;
  max_monthly_loss_pct?: number;
  move_to_breakeven_after_rr?: number;
  trailing_after_rr?: number;
  trailing_atr_multiplier?: number;
  check_atr?: boolean;
  min_atr_to_stop_ratio?: number;
  long_only?: boolean;
  short_only?: boolean;
  intraday_only?: boolean;
}

export interface DirectionSpec {
  long: boolean;
  short: boolean;
}

export interface StrategyMetadata {
  name: string;
  display_name: string;
  description: string;
  source: 'python' | 'builtin' | 'custom';
  is_custom: boolean;
  custom_id: number | null;
  params: StrategyParamSpec[];
  default_risk_config: RiskConfigPreview;
  direction: DirectionSpec;
  tags: string[];
  intraday_only: boolean;
}

export interface StrategyListResponse {
  items: StrategyMetadata[];
  total: number;
}