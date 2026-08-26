import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.verification.engine import ConfidenceResult
from app.models.verification import ConfidenceScore, Evidence


async def add_evidence(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    source_url: str,
    domain: str,
    excerpt: str | None,
) -> Evidence:
    ev = Evidence(
        organization_id=organization_id,
        company_id=company_id,
        source_url=source_url,
        domain=domain,
        excerpt=excerpt,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


async def add_confidence_score(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    result: ConfidenceResult,
) -> ConfidenceScore:
    score = ConfidenceScore(
        organization_id=organization_id,
        company_id=company_id,
        status=result.status,
        source_count=result.source_count,
        source_diversity=result.source_diversity,
        freshness_score=result.freshness_score,
        evidence_completeness=result.evidence_completeness,
        overall_score=result.overall_score,
    )
    db.add(score)
    await db.commit()
    await db.refresh(score)
    return score
