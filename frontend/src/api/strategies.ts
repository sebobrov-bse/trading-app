import { apiGet } from './client';
import type { StrategyListResponse, StrategyMetadata } from './types';

export function getStrategies(): Promise<StrategyListResponse> {
  return apiGet<StrategyListResponse>('/strategies');
}

export function getStrategy(name: string): Promise<StrategyMetadata> {
  return apiGet<StrategyMetadata>(`/strategies/${encodeURIComponent(name)}`);
}