from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.exceptions import GoldMineError, goldmine_error_handler, unhandled_error_handler
from app.logging_config import setup_logging, get_logger
from app.api.health import router as health_router
from app.api.data import router as data_router
from app.api.files import router as files_router
from app.api.entities import router as entities_router
from app.api.views import router as views_router
from app.api.documents import router as documents_router
from app.auth.router import router as auth_router
from app.auth.middleware import AuthMiddleware
from app.api.schedules import router as schedules_router
from app.email.scheduler import start_scheduler

setup_logging()
logger = get_logger(__name__)


def create_app() -> FastAPI:
    application = FastAPI(title="GoldMine API", version="0.1.0")

    application.add_middleware(AuthMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.add_exception_handler(GoldMineError, goldmine_error_handler)
    application.add_exception_handler(Exception, unhandled_error_handler)

    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(data_router)
    application.include_router(files_router)
    application.include_router(entities_router)
    application.include_router(views_router)
    application.include_router(documents_router)
    application.include_router(schedules_router)

    start_scheduler(application)

    logger.info("app_started", env=settings.ENV)
    return application


app = create_app()
