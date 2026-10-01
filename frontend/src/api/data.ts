import { apiDelete, apiGet, apiPostWithTimeout } from './client';
import type {
  DataSummaryResponse,
  DeleteResponse,
  LoadReport,
  LoadRequest,
} from './types';

const LOAD_TIMEOUT_MS = 60_000;

export function loadHistory(req: LoadRequest): Promise<LoadReport> {
  return apiPostWithTimeout<LoadReport>('/data/load', req, LOAD_TIMEOUT_MS);
}

export function getSummary(params?: {
  symbol?: string;
  timeframe?: number;
}): Promise<DataSummaryResponse> {
  const query = new URLSearchParams();
  if (params?.symbol) query.set('symbol', params.symbol);
  if (params?.timeframe) query.set('timeframe', String(params.timeframe));
  const qs = query.toString();
  return apiGet<DataSummaryResponse>(`/data/summary${qs ? `?${qs}` : ''}`);
}

export function deleteData(
  symbol: string,
  timeframe: number,
): Promise<DeleteResponse> {
  return apiDelete<DeleteResponse>(`/data/${symbol}/${timeframe}`);
}