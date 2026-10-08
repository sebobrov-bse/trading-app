interface StrategyLoadErrorProps {
  message: string;
  onRetry: () => void;
}

export function StrategyLoadError({ message, onRetry }: StrategyLoadErrorProps) {
  return (
    <div className="strategy-load-error">
      <h3>Не удалось загрузить список стратегий</h3>
      <p className="error-box">{message}</p>
      <div className="strategy-load-error-actions">
        <button type="button" className="btn-primary" onClick={onRetry}>
          Повторить
        </button>
        <a
          href="/api/v1/health"
          target="_blank"
          rel="noopener noreferrer"
          className="btn-secondary"
        >
          Проверить бэкенд
        </a>
      </div>
      <p className="muted">
        Убедись, что backend запущен на порту 8000.
      </p>
    </div>
  );
}