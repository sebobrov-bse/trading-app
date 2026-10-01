import type { LoadReport } from '../api/types';

interface LoadResultMessageProps {
  report: LoadReport;
  onDismiss: () => void;
}

export function LoadResultMessage({
  report,
  onDismiss,
}: LoadResultMessageProps) {
  const allDuplicates = report.inserted === 0 && report.fetched > 0;

  return (
    <div
      className={`load-result ${
        allDuplicates ? 'load-result-info' : 'load-result-ok'
      }`}
    >
      <div>
        <strong>
          Loaded {report.symbol} (tf={report.timeframe}):
        </strong>{' '}
        fetched {report.fetched}, inserted {report.inserted}, skipped{' '}
        {report.duplicates_skipped}, took {report.duration_seconds.toFixed(2)}s
        {allDuplicates && (
          <p className="muted" style={{ margin: '4px 0 0' }}>
            All data was already in DB. Duplicates skipped — this is fine.
          </p>
        )}
      </div>
      <button type="button" onClick={onDismiss} className="btn-close">
        Dismiss
      </button>
    </div>
  );
}