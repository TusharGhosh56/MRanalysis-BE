from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import DbSession, get_current_user
from app.core.security import PasswordValidationError
from app.models.user import User
from app.schemas.auth import (
    GoogleAuthRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidGoogleTokenError,
    authenticate_google_user,
    authenticate_user,
    issue_access_token,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
def register(payload: RegisterRequest, db: DbSession) -> User:
    try:
        return register_user(db, email=payload.email, password=payload.password)
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from None
    except PasswordValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive a JWT access token",
)
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    try:
        user = authenticate_user(db, email=payload.email, password=payload.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    return issue_access_token(user)


@router.post(
    "/google",
    response_model=TokenResponse,
    summary="Authenticate with Google and receive a JWT access token",
)
def google_auth(payload: GoogleAuthRequest, db: DbSession) -> TokenResponse:
    try:
        user = authenticate_google_user(db, payload=payload)
    except InvalidGoogleTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return issue_access_token(user)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the currently authenticated user",
)
def me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user
