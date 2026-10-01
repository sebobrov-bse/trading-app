import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';

interface WidgetCardProps {
  title: string;
  actionLabel?: string;
  actionTo?: string;
  children: ReactNode;
}

export function WidgetCard({
  title,
  actionLabel,
  actionTo,
  children,
}: WidgetCardProps) {
  return (
    <div className="widget-card">
      <div className="widget-header">
        <h3>{title}</h3>
        {actionLabel && actionTo && (
          <Link to={actionTo} className="link">
            {actionLabel} →
          </Link>
        )}
      </div>
      <div className="widget-body">{children}</div>
    </div>
  );
}