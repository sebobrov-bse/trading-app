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