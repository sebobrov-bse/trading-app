import { apiDelete, apiGet, apiPost } from './client';
import type {
  BacktestHistoryResponse,
  BacktestRequest,
  BacktestResult,
} from './types';

export function runBacktest(request: BacktestRequest): Promise<BacktestResult> {
  return apiPost<BacktestResult>('/backtest/run', request);
}

export function getBacktestHistory(params?: {
  symbol?: string;
  strategy?: string;
  limit?: number;
  offset?: number;
}): Promise<BacktestHistoryResponse> {
  const query = new URLSearchParams();
  if (params?.symbol) query.set('symbol', params.symbol);
  if (params?.strategy) query.set('strategy', params.strategy);
  if (params?.limit) query.set('limit', String(params.limit));
  if (params?.offset) query.set('offset', String(params.offset));
  const qs = query.toString();
  return apiGet<BacktestHistoryResponse>(
    `/backtest/history${qs ? `?${qs}` : ''}`,
  );
}

export function getBacktest(id: number): Promise<BacktestResult> {
  return apiGet<BacktestResult>(`/backtest/${id}`);
}

export function deleteBacktest(id: number): Promise<void> {
  return apiDelete(`/backtest/${id}`);
}