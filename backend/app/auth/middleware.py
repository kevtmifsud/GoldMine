from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.auth.service import decode_token
from app.exceptions import AuthenticationError
from app.logging_config import get_logger

logger = get_logger(__name__)

COOKIE_NAME = "goldmine_token"

PUBLIC_PATHS = {
    "/auth/login",
    "/auth/logout",
    "/api/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        if path in PUBLIC_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)
        if not token:
            logger.warning("auth_missing", path=path)
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

        try:
            user = decode_token(token)
            request.state.user = user
        except AuthenticationError:
            logger.warning("auth_invalid_token", path=path)
            return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})

        return await call_next(request)
