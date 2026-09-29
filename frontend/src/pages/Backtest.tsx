import { useState } from 'react';
import type { BacktestResult } from '../api/types';
import { BacktestForm } from '../components/BacktestForm';
import { BacktestResults } from '../components/BacktestResults';

export function Backtest() {
  const [result, setResult] = useState<BacktestResult | null>(null);

  return (
    <div className="page">
      <h1>Run Backtest</h1>
      <BacktestForm onSuccess={setResult} />
      {result && <BacktestResults result={result} />}
    </div>
  );
}