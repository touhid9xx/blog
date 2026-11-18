from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserPublic,
)
from app.services import auth_service
from app.services.auth_service import AuthError

router = APIRouter(prefix="/auth", tags=["auth"])


def _map_auth_error(e: AuthError) -> HTTPException:
    mapping = {
        "email_taken": status.HTTP_409_CONFLICT,
        "invalid_credentials": status.HTTP_401_UNAUTHORIZED,
        "account_disabled": status.HTTP_403_FORBIDDEN,
        "invalid_refresh": status.HTTP_401_UNAUTHORIZED,
        "account_unavailable": status.HTTP_403_FORBIDDEN,
    }
    return HTTPException(
        status_code=mapping.get(e.code, status.HTTP_400_BAD_REQUEST),
        detail={"code": e.code, "message": e.message},
    )


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> UserPublic:
    try:
        user = await auth_service.register_user(session, email=body.email, password=body.password)
    except AuthError as e:
        raise _map_auth_error(e) from e
    return UserPublic.model_validate(user)


@router.post("/login", response_model=TokenPair)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenPair:
    try:
        user = await auth_service.authenticate(session, email=body.email, password=body.password)
    except AuthError as e:
        raise _map_auth_error(e) from e
    return auth_service.issue_tokens_for(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenPair:
    try:
        return await auth_service.refresh_tokens(session, refresh_token=body.refresh_token)
    except AuthError as e:
        raise _map_auth_error(e) from e


@router.get("/me", response_model=UserPublic)
async def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)
