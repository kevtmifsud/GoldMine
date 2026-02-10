from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.logging_config import get_logger

logger = get_logger(__name__)


class GoldMineError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthenticationError(GoldMineError):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status_code=401)


class DataAccessError(GoldMineError):
    def __init__(self, message: str = "Data access error"):
        super().__init__(message, status_code=500)


class NotFoundError(GoldMineError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)


async def goldmine_error_handler(request: Request, exc: GoldMineError) -> JSONResponse:
    logger.error("application_error", error=exc.message, status_code=exc.status_code, path=str(request.url))
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", error=str(exc), path=str(request.url))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
