import asyncio
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password, needs_rehash, verify_password
from app.core.tokens import TokenError, create_access_token, create_refresh_token, decode_refresh
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import TokenPair
from app.services import users_repo


class AuthError(Exception):
    def __init__(self, message: str, *, code: str = "auth_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def _pair_for(user: User) -> TokenPair:
    settings = get_settings()
    return TokenPair(
        access_token=create_access_token(str(user.id), user.role.value),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def register_user(session: AsyncSession, *, email: str, password: str) -> User:
    existing = await users_repo.get_by_email(session, email)
    if existing is not None:
        raise AuthError("email already registered", code="email_taken")

    pw_hash = await asyncio.to_thread(hash_password, password)
    try:
        user = await users_repo.create_user(
            session, email=email, password_hash=pw_hash, role=UserRole.CUSTOMER
        )
        await session.commit()
        await session.refresh(user)
        return user
    except IntegrityError as e:
        await session.rollback()
        raise AuthError("email already registered", code="email_taken") from e


async def authenticate(session: AsyncSession, *, email: str, password: str) -> User:
    user = await users_repo.get_by_email(session, email)
    if user is None:
        await asyncio.to_thread(
            verify_password,
            password,
            "$argon2id$v=19$m=65536,t=3,p=4$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        )
        raise AuthError("invalid credentials", code="invalid_credentials")
    if not user.is_active:
        raise AuthError("account disabled", code="account_disabled")

    ok = await asyncio.to_thread(verify_password, password, user.password_hash)
    if not ok:
        raise AuthError("invalid credentials", code="invalid_credentials")

    if await asyncio.to_thread(needs_rehash, user.password_hash):
        user.password_hash = await asyncio.to_thread(hash_password, password)
        await session.commit()

    return user


def issue_tokens_for(user: User) -> TokenPair:
    return _pair_for(user)


async def refresh_tokens(session: AsyncSession, *, refresh_token: str) -> TokenPair:
    try:
        payload = decode_refresh(refresh_token)
    except TokenError as e:
        raise AuthError("invalid refresh token", code="invalid_refresh") from e

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as e:
        raise AuthError("invalid refresh token", code="invalid_refresh") from e

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthError("account unavailable", code="account_unavailable")

    return _pair_for(user)
