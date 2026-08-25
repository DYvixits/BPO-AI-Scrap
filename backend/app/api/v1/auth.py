from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import AuthContext, get_current_auth
from app.models.organization import Organization
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    OrganizationOut,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenPair, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    return await auth_service.register(db, payload)


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    return await auth_service.login(db, email=payload.email, password=payload.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    return await auth_service.refresh(db, refresh_token=payload.refresh_token)


@router.get("/me", response_model=MeResponse)
async def me(
    auth: AuthContext = Depends(get_current_auth), db: AsyncSession = Depends(get_db)
) -> MeResponse:
    organization = await db.get(Organization, auth.organization_id)
    return MeResponse(
        id=auth.user.id,
        email=auth.user.email,
        full_name=auth.user.full_name,
        organization=OrganizationOut.model_validate(organization),
        role=auth.role,
    )
