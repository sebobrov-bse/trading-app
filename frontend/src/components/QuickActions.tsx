import { Link } from 'react-router-dom';

export function QuickActions() {
  return (
    <div className="quick-actions">
      <Link to="/backtest" className="quick-action">
        <span className="quick-icon">▶</span>
        <span>Run Backtest</span>
      </Link>
      <Link to="/data" className="quick-action">
        <span className="quick-icon">↓</span>
        <span>Load Data</span>
      </Link>
      <Link to="/history" className="quick-action">
        <span className="quick-icon">☰</span>
        <span>History</span>
      </Link>
    </div>
  );
}