from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, set_tenant_context
from app.core.security import InvalidTokenError, TokenType, decode_token
from app.models.organization import OrganizationMember, Role
from app.models.user import User

_bearer_scheme = HTTPBearer(auto_error=False)


class AuthContext:
    """Everything a request handler needs about the authenticated caller.

    Resolved once per request from the JWT — org scoping is never taken from
    a client-supplied query/body parameter, so there is no code path that lets
    one organization read another's data.
    """

    def __init__(self, user: User, organization_id: UUID, role: Role) -> None:
        self.user = user
        self.organization_id = organization_id
        self.role = role


async def get_current_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    try:
        payload = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
    except InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc

    user_id = UUID(payload["sub"])
    organization_id = UUID(payload["org"])

    # Must happen before this session's first query (see
    # app/core/database.py::set_tenant_context) so PostgreSQL RLS is active
    # for every tenant-scoped table this request touches, including this
    # dependency's own membership check below.
    set_tenant_context(db, organization_id)

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    membership = await db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.organization_id == organization_id,
        )
    )
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No membership in this organization")

    # membership.role is read fresh from the DB rather than trusted from the
    # JWT's own "role" claim, so a role change takes effect immediately
    # instead of waiting for the access token to expire.
    return AuthContext(user=user, organization_id=organization_id, role=membership.role)


_ROLE_RANK: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.API_CLIENT: 1,
    Role.ANALYST: 2,
    Role.RESEARCHER: 3,
    Role.RESEARCH_MANAGER: 4,
    Role.ADMIN: 5,
    Role.SUPER_ADMIN: 6,
}


def require_role(minimum: Role) -> Callable[[AuthContext], AuthContext]:
    """FastAPI dependency factory: reject callers below the given role rank."""

    def _check(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
        if _ROLE_RANK[auth.role] < _ROLE_RANK[minimum]:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Requires role {minimum.value!r} or higher"
            )
        return auth

    return _check
