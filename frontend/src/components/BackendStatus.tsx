interface BackendStatusProps {
  status: 'loading' | 'ok' | 'error';
  database?: string;
  errorMessage?: string;
}

export function BackendStatus({
  status,
  database,
  errorMessage,
}: BackendStatusProps) {
  if (status === 'loading') {
    return (
      <div className="backend-status">
        <span className="status-dot status-dot-loading" />
        Checking backend...
      </div>
    );
  }

  if (status === 'ok') {
    return (
      <div className="backend-status">
        <span className="status-dot status-dot-ok" />
        Backend OK{database ? ` · db: ${database}` : ''}
      </div>
    );
  }

  return (
    <div className="backend-status" title={errorMessage}>
      <span className="status-dot status-dot-error" />
      Backend unavailable
    </div>
  );
}