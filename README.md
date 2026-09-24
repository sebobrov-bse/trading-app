# Trading App

Торговое ПО на Python: FastAPI + SQLite + Backtrader.

## Требования

- Python 3.11+
- Git

## Установка

    python -m venv .venv
    .venv\Scripts\activate
    pip install -e .

## Запуск

    uvicorn app.main:app --reload

Открой http://127.0.0.1:8000/health — должен вернуться {"status": "ok"}.

## Структура

- app/api/ — HTTP-роуты
- app/services/ — бизнес-логика
- app/repositories/ — доступ к данным
- app/models/ — SQLAlchemy-модели
- app/schemas/ — Pydantic-схемы
- app/data_providers/ — адаптеры источников данных
- app/brokers/ — адаптеры брокеров
- app/strategies/ — торговые стратегии
- app/backtest/ — движок бэктеста
- tests/ — тесты
- frontend/ — будущий React-фронт
