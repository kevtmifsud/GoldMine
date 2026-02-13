from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.auth.models import UserInfo
from app.auth.users import USERS
from app.config.settings import settings
from app.exceptions import AuthenticationError
from app.logging_config import get_logger

logger = get_logger(__name__)


def validate_credentials(username: str, password: str) -> UserInfo:
    user = USERS.get(username)
    if not user:
        logger.warning("login_failed", username=username, reason="unknown_user")
        raise AuthenticationError("Invalid username or password")

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        logger.warning("login_failed", username=username, reason="bad_password")
        raise AuthenticationError("Invalid username or password")

    logger.info("login_success", username=username)
    return UserInfo(
        username=user["username"],
        display_name=user["display_name"],
        role=user["role"],
        email=user.get("email", ""),
    )


def create_token(user: UserInfo) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    payload = {
        "sub": user.username,
        "name": user.display_name,
        "role": user.role,
        "email": user.email,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> UserInfo:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return UserInfo(
            username=payload["sub"],
            display_name=payload["name"],
            role=payload["role"],
            email=payload.get("email", ""),
        )
    except JWTError as e:
        raise AuthenticationError(f"Invalid token: {e}")
