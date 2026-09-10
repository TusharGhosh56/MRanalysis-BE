from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import TokenResponse


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register_user(db: Session, *, email: str, password: str) -> User:
    normalized_email = normalize_email(email)
    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise EmailAlreadyRegisteredError from exc
    db.refresh(user)
    return user


def authenticate_user(db: Session, *, email: str, password: str) -> User:
    normalized_email = normalize_email(email)
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError
    return user


def issue_access_token(user: User) -> TokenResponse:
    token = create_access_token(subject=user.id)
    return TokenResponse(access_token=token)


def get_user_by_id(db: Session, user_id: UUID) -> User | None:
    return db.get(User, user_id)


class InvalidGoogleTokenError(Exception):
    pass


def get_or_create_google_user(db: Session, *, email: str) -> User:
    import secrets

    normalized_email = normalize_email(email)
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is not None:
        return user

    random_password = secrets.token_urlsafe(32)
    user = User(
        email=normalized_email,
        password_hash=hash_password(random_password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        user = db.scalar(select(User).where(User.email == normalized_email))
        if user is not None:
            return user
        raise
    db.refresh(user)
    return user


def verify_google_token_or_code(payload: object) -> str:
    import httpx
    from app.config import get_settings

    settings = get_settings()

    credential = getattr(payload, "credential", None)
    id_token = getattr(payload, "id_token", None) or getattr(payload, "token", None) or credential
    code = getattr(payload, "code", None)

    # 1. If an authorization code was provided, exchange it for tokens
    if not id_token and code:
        client_id = settings.GOOGLE_CLIENT_ID.strip()
        client_secret = settings.GOOGLE_CLIENT_SECRET.strip()
        redirect_uri = getattr(payload, "redirect_uri", None) or "postmessage"

        try:
            exchange_resp = httpx.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=15.0,
            )
            if exchange_resp.status_code != 200:
                raise InvalidGoogleTokenError(
                    f"Failed to exchange authorization code with Google: {exchange_resp.text}"
                )
            token_data = exchange_resp.json()
            id_token = token_data.get("id_token")
        except Exception as exc:
            if isinstance(exc, InvalidGoogleTokenError):
                raise
            raise InvalidGoogleTokenError(f"Error during Google code exchange: {exc}") from exc

    if not id_token:
        raise InvalidGoogleTokenError("Google credential or authorization code is required")

    # 2. Verify Google ID token
    try:
        resp = httpx.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
            timeout=15.0,
        )
        if resp.status_code != 200:
            raise InvalidGoogleTokenError("Invalid or expired Google ID token")
        info = resp.json()
    except Exception as exc:
        if isinstance(exc, InvalidGoogleTokenError):
            raise
        raise InvalidGoogleTokenError(f"Failed to verify Google token: {exc}") from exc

    # 3. Validate issuer
    iss = info.get("iss")
    if iss not in ("accounts.google.com", "https://accounts.google.com"):
        raise InvalidGoogleTokenError("Invalid Google token issuer")

    # 4. Validate audience if client ID is configured
    client_id = settings.GOOGLE_CLIENT_ID.strip()
    if client_id:
        aud = info.get("aud")
        azp = info.get("azp")
        if aud != client_id and azp != client_id:
            raise InvalidGoogleTokenError("Google token audience mismatch with configured client ID")

    # 5. Check email
    email = info.get("email")
    if not email:
        raise InvalidGoogleTokenError("Google token did not contain an email address")

    email_verified = info.get("email_verified")
    if email_verified not in (True, "true", "True", 1, "1"):
        raise InvalidGoogleTokenError("Google email is not verified")

    return str(email)


def authenticate_google_user(db: Session, *, payload: object) -> User:
    email = verify_google_token_or_code(payload)
    return get_or_create_google_user(db, email=email)

