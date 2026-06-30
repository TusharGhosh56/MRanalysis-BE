import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError

from app.config import get_settings

settings = get_settings()

# bcrypt truncates passwords longer than 72 bytes; pre-hash with SHA-256 is an option,
# but for v1 we enforce a reasonable max length aligned with common practice.
PASSWORD_MAX_LENGTH = 128
_PASSWORD_HAS_LETTER = re.compile(r"[A-Za-z]")
_PASSWORD_HAS_DIGIT = re.compile(r"\d")


class PasswordValidationError(ValueError):
    pass


def validate_password_strength(password: str) -> None:
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        raise PasswordValidationError(
            f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters long"
        )
    if len(password) > PASSWORD_MAX_LENGTH:
        raise PasswordValidationError(
            f"Password must be at most {PASSWORD_MAX_LENGTH} characters long"
        )
    if not _PASSWORD_HAS_LETTER.search(password):
        raise PasswordValidationError("Password must contain at least one letter")
    if not _PASSWORD_HAS_DIGIT.search(password):
        raise PasswordValidationError("Password must contain at least one digit")


def hash_password(password: str) -> str:
    validate_password_strength(password)
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except ValueError:
        return False


def create_access_token(*, subject: UUID) -> str:
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": now,
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except InvalidTokenError as exc:
        raise ValueError("Invalid or expired token") from exc

    if payload.get("type") != "access":
        raise ValueError("Invalid token type")

    return payload
