import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import AuthContext, get_current_auth
from app.core.redis import get_redis_pool, research_channel
from app.repositories import research_repository
from app.schemas.research import (
    ResearchCreateRequest,
    ResearchEventOut,
    ResearchJobDetailOut,
    ResearchJobOut,
    ResearchResultOut,
)
from app.services.research_orchestrator import create_and_enqueue

router = APIRouter(prefix="/research", tags=["research"])


@router.post("", response_model=ResearchJobOut, status_code=status.HTTP_201_CREATED)
async def create_research(
    payload: ResearchCreateRequest,
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
) -> ResearchJobOut:
    job = await create_and_enqueue(
        db,
        organization_id=auth.organization_id,
        created_by=auth.user.id,
        query=payload.query,
        mode=payload.mode,
        config_overrides=payload.config,
    )
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
