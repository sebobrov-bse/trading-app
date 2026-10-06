import type { BacktestForCompare, CommonPeriod } from '../api/types';

interface PeriodWarningProps {
  backtests: BacktestForCompare[];
  commonPeriod: CommonPeriod;
}

export function PeriodWarning({ backtests, commonPeriod }: PeriodWarningProps) {
  // Are all periods identical?
  const firstStart = backtests[0]?.start;
  const firstEnd = backtests[0]?.end;
  const allSame = backtests.every(
    (b) => b.start === firstStart && b.end === firstEnd,
  );

  if (allSame) return null;

  return (
    <div className="period-warning">
      <strong>Backtests on different periods.</strong> Common overlapping
      period: {commonPeriod.start} → {commonPeriod.end}. Metrics may not be
      directly comparable.
    </div>
  );
}