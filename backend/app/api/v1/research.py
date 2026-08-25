import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import AuthContext, get_current_auth
from app.core.redis import get_redis_pool, research_channel
from app.repositories import entity_repository, research_repository
from app.schemas.entity import CompanyOut
from app.schemas.research import (
    ResearchCreateRequest,
    ResearchEventOut,
    ResearchJobDetailOut,
    ResearchJobOut,
    ResearchResultOut,
)
from app.services.research_orchestrator import QuotaExceededError, create_and_enqueue

router = APIRouter(prefix="/research", tags=["research"])


@router.post("", response_model=ResearchJobOut, status_code=status.HTTP_201_CREATED)
async def create_research(
    payload: ResearchCreateRequest,
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
) -> ResearchJobOut:
    try:
        job = await create_and_enqueue(
            db,
            organization_id=auth.organization_id,
            created_by=auth.user.id,
            query=payload.query,
            mode=payload.mode,
            config_overrides=payload.config,
        )
    except QuotaExceededError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"{exc} — wait for a running research job to finish, or upgrade your plan.",
        ) from exc
    return ResearchJobOut.model_validate(job)


@router.get("", response_model=list[ResearchJobOut])
async def list_research(
    auth: AuthContext = Depends(get_current_auth), db: AsyncSession = Depends(get_db)
) -> list[ResearchJobOut]:
    jobs = await research_repository.list_research_jobs(db, organization_id=auth.organization_id)
    return [ResearchJobOut.model_validate(job) for job in jobs]


@router.get("/{job_id}", response_model=ResearchJobDetailOut)
async def get_research(
    job_id: UUID,
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
) -> ResearchJobDetailOut:
    job = await research_repository.get_research_job(
        db, organization_id=auth.organization_id, job_id=job_id, with_events=True
    )
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Research job not found")
    return ResearchJobDetailOut(
        **ResearchJobOut.model_validate(job).model_dump(),
        events=[ResearchEventOut.model_validate(e) for e in job.events],
    )


@router.get("/{job_id}/results", response_model=list[ResearchResultOut])
async def get_research_results(
    job_id: UUID,
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
) -> list[ResearchResultOut]:
    results = await research_repository.list_research_results(
        db, organization_id=auth.organization_id, job_id=job_id
    )
    return [ResearchResultOut.model_validate(r) for r in results]


@router.get("/{job_id}/companies", response_model=list[CompanyOut])
async def get_research_companies(
    job_id: UUID,
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
) -> list[CompanyOut]:
    """Entity Resolution's output for this job (app/engines/entity_
    resolution): every crawled page grouped into the company it was
    resolved to belong to, with the literal name/domain variants
    (`aliases`) that justified each grouping. Empty until the job reaches
    CRAWLING's end — see the `entities.resolved` event."""
    job = await research_repository.get_research_job(
        db, organization_id=auth.organization_id, job_id=job_id
    )
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Research job not found")
    companies = await entity_repository.list_companies_for_job(
        db, organization_id=auth.organization_id, job_id=job_id
    )
    return [CompanyOut.model_validate(c) for c in companies]


@router.websocket("/{job_id}/ws")
async def research_ws(websocket: WebSocket, job_id: UUID) -> None:
    """Live progress feed. Auth is via a `token` query param since browser
    WebSocket clients cannot set an Authorization header — the same JWT
    access token used for REST calls is accepted here and validated the same
    way, including organization-scoped access to this specific job."""
    from app.core import database as database_module
    from app.core.security import InvalidTokenError, TokenType, decode_token

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        payload = decode_token(token, expected_type=TokenType.ACCESS)
    except InvalidTokenError:
        await websocket.close(code=4401)
        return

    organization_id = UUID(payload["org"])
    async with database_module.async_session_factory() as db:
        database_module.set_tenant_context(db, organization_id)
        job = await research_repository.get_research_job(
            db, organization_id=organization_id, job_id=job_id
        )
    if job is None:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    redis = get_redis_pool()
    pubsub = redis.pubsub()
    await pubsub.subscribe(research_channel(str(job_id)))

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            await websocket.send_text(message["data"])
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        await pubsub.unsubscribe(research_channel(str(job_id)))
        await pubsub.aclose()
