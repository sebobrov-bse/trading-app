import { apiGet } from './client';
import type { CandleListResponse } from './types';

export function getCandles(params: {
  symbol: string;
  timeframe: number;
  limit?: number;
  offset?: number;
  order?: 'asc' | 'desc';
}): Promise<CandleListResponse> {
  const query = new URLSearchParams({
    symbol: params.symbol,
    timeframe: String(params.timeframe),
  });
  if (params.limit) query.set('limit', String(params.limit));
  if (params.offset) query.set('offset', String(params.offset));
  if (params.order) query.set('order', params.order);
  return apiGet<CandleListResponse>(`/candles?${query.toString()}`);
}