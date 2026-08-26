import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entity import Company, EntityAlias
from app.models.research import ResearchResult


async def add_company(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    canonical_name: str,
    primary_domain: str,
    description: str | None,
    match_confidence: float,
) -> Company:
    company = Company(
        organization_id=organization_id,
        research_job_id=job_id,
        canonical_name=canonical_name,
        primary_domain=primary_domain,
        description=description,
        match_confidence=match_confidence,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


async def add_alias(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    alias_type: str,
    value: str,
    source_url: str,
) -> EntityAlias:
    alias = EntityAlias(
        organization_id=organization_id,
        company_id=company_id,
        alias_type=alias_type,
        value=value,
        source_url=source_url,
    )
    db.add(alias)
    await db.commit()
    await db.refresh(alias)
    return alias


async def set_results_company(
    db: AsyncSession, *, job_id: uuid.UUID, urls: list[str], company_id: uuid.UUID
) -> None:
    """Points every research_results row for this job whose url is in
    `urls` at the resolved company. One statement, not one write per URL —
    a job's result count is small, but there's no reason to round-trip
    per row when SQLAlchemy can do it in one UPDATE."""
    if not urls:
        return
    result = await db.scalars(
        select(ResearchResult).where(
            ResearchResult.research_job_id == job_id, ResearchResult.url.in_(urls)
        )
    )
    for row in result.all():
        row.company_id = company_id
    await db.commit()


async def list_companies_for_job(
    db: AsyncSession, *, organization_id: uuid.UUID, job_id: uuid.UUID
) -> list[Company]:
    stmt = (
        select(Company)
        .where(Company.organization_id == organization_id, Company.research_job_id == job_id)
        .options(
            selectinload(Company.aliases),
            selectinload(Company.evidence),
            selectinload(Company.confidence_score),
            selectinload(Company.signals),
            selectinload(Company.fit_score),
            selectinload(Company.intent_score),
            selectinload(Company.opportunity_score),
        )
        .order_by(Company.canonical_name)
    )
    result = await db.scalars(stmt)
    return list(result.all())
