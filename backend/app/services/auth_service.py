from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.auth_repository import (
    create_user_and_organization,
    get_primary_membership,
    get_user_by_email,
)
from app.schemas.auth import RegisterRequest, TokenPair


async def register(db: AsyncSession, payload: RegisterRequest) -> TokenPair:
    if await get_user_by_email(db, payload.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user, organization, role = await create_user_and_organization(
        db,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        organization_name=payload.organization_name,
    )
    return _issue_tokens(user_id=user.id, organization_id=organization.id, role=role.value)


async def login(db: AsyncSession, *, email: str, password: str) -> TokenPair:
    user = await get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")

    membership = await get_primary_membership(db, user.id)
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User has no organization")

    return _issue_tokens(
        user_id=user.id, organization_id=membership.organization_id, role=membership.role.value
    )


async def refresh(db: AsyncSession, *, refresh_token: str) -> TokenPair:
    try:
        payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
    except InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid refresh token: {exc}") from exc

    user_id = UUID(payload["sub"])
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    membership = await get_primary_membership(db, user_id)
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User has no organization")

    return _issue_tokens(
        user_id=user.id, organization_id=membership.organization_id, role=membership.role.value
    )


def _issue_tokens(*, user_id: UUID, organization_id: UUID, role: str) -> TokenPair:
    access = create_access_token(user_id=user_id, organization_id=organization_id, role=role)
    refresh_tok = create_refresh_token(user_id=user_id)
    return TokenPair(access_token=access, refresh_token=refresh_tok)
