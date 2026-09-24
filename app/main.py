from fastapi import FastAPI

from app.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
)


@app.get("/health")
def health() -> dict[str, str]:
    """Проверка живости приложения."""
    return {"status": "ok"}
