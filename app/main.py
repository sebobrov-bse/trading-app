from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import api_v1_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown hooks.

    Startup runs before yield. Shutdown runs after yield.
    Tables are created by Alembic, DB ping is in /health.
    Add HTTP clients to exchanges here later.
    """
    # Startup
    yield
    # Shutdown


def create_app() -> FastAPI:
    """App factory: builds and configures the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.include_router(api_v1_router)

    return app


app = create_app()