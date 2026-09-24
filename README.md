# Trading App

Trading software: FastAPI + SQLite + Backtrader.

## Requirements

- Python 3.11+
- Git

## Install

    python -m venv .venv
    .venv\Scripts\activate
    pip install -e ".[dev]"

## Run

    uvicorn app.main:app --reload

Open http://127.0.0.1:8000/health — should return {"status": "ok"}.

## Structure

- app/api/ — HTTP routes
- app/services/ — business logic
- app/repositories/ — data access
- app/models/ — SQLAlchemy models
- app/schemas/ — Pydantic schemas
- app/data_providers/ — market data adapters
- app/brokers/ — broker adapters
- app/strategies/ — trading strategies
- app/backtest/ — backtest engine
- tests/ — tests
- frontend/ — future React frontend