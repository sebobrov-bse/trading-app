interface MetricCardProps {
  label: string;
  value: string;
  hint?: string;
  variant?: 'default' | 'positive' | 'negative';
}

export function MetricCard({
  label,
  value,
  hint,
  variant = 'default',
}: MetricCardProps) {
  return (
    <div className={`metric-card metric-card-${variant}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {hint && <div className="metric-hint">{hint}</div>}
    </div>
  );
}