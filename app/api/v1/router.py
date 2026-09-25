from fastapi import APIRouter

from app.api.v1.endpoints import db_check, health

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(health.router)
api_v1_router.include_router(db_check.router)