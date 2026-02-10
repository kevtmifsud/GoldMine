from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.auth.models import LoginRequest, UserInfo
from app.auth.service import create_token, validate_credentials
from app.config.settings import settings
from app.exceptions import AuthenticationError

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "goldmine_token"


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> dict:
    user = validate_credentials(body.username, body.password)
    token = create_token(user)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.ENV == "production",
        max_age=settings.JWT_EXPIRATION_HOURS * 3600,
    )
    return {"message": "Login successful", "user": user.model_dump()}


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(key=COOKIE_NAME)
    return {"message": "Logged out"}


@router.get("/me")
async def get_current_user(request: Request) -> UserInfo:
    user: UserInfo | None = getattr(request.state, "user", None)
    if not user:
        raise AuthenticationError("Not authenticated")
    return user
