import { useEffect, useState } from 'react';
import { getHealth } from '../api/health';

export function Dashboard() {
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');
  const [database, setDatabase] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string>('');

  useEffect(() => {
    getHealth()
      .then((data) => {
        setStatus('ok');
        setDatabase(data.database);
      })
      .catch((err) => {
        setStatus('error');
        setErrorMsg(err instanceof Error ? err.message : String(err));
      });
  }, []);

  return (
    <div className="page">
      <h1>Dashboard</h1>
      <p>Backend status:</p>
      {status === 'loading' && <p>Loading...</p>}
      {status === 'ok' && (
        <p className="status-ok">
          Backend: <strong>OK</strong> (database: {database})
        </p>
      )}
      {status === 'error' && (
        <p className="status-error">
          Backend: <strong>unavailable</strong> — {errorMsg}
        </p>
      )}
    </div>
  );
}