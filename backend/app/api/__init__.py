from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.transactions import router as transactions_router
from app.api.vehicles import router as vehicles_router
from app.api.devices import router as devices_router
from app.api.exceptions import router as exceptions_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(transactions_router)
api_router.include_router(vehicles_router)
api_router.include_router(devices_router)
api_router.include_router(exceptions_router)