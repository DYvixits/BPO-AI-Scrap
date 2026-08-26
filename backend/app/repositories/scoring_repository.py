import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.fit_scoring.engine import FitResult
from app.engines.intent_scoring.engine import IntentResult
from app.engines.opportunity_scoring.engine import OpportunityResult
from app.models.scoring import FitScore, IntentScore, OpportunityScore


async def add_fit_score(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    result: FitResult,
) -> FitScore:
    fit_score = FitScore(
        organization_id=organization_id,
        company_id=company_id,
        research_job_id=job_id,
        score=result.score,
        matched_factors=result.matched_factors,
        unmatched_factors=result.unmatched_factors,
    )
    db.add(fit_score)
    await db.commit()
    await db.refresh(fit_score)
    return fit_score


async def add_intent_score(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    result: IntentResult,
) -> IntentScore:
    intent_score = IntentScore(
        organization_id=organization_id,
        company_id=company_id,
        research_job_id=job_id,
        score=result.score,
        contributing_signals=result.contributing_signals,
    )
    db.add(intent_score)
    await db.commit()
    await db.refresh(intent_score)
    return intent_score


async def add_opportunity_score(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    fit_score_id: uuid.UUID,
    intent_score_id: uuid.UUID,
    confidence_score_id: uuid.UUID,
    result: OpportunityResult,
) -> OpportunityScore:
    opportunity_score = OpportunityScore(
        organization_id=organization_id,
        company_id=company_id,
        research_job_id=job_id,
        fit_score_id=fit_score_id,
        intent_score_id=intent_score_id,
        confidence_score_id=confidence_score_id,
        score=result.score,
        fit_component=result.fit_component,
        intent_component=result.intent_component,
        confidence_component=result.confidence_component,
        freshness_component=result.freshness_component,
        momentum_component=result.momentum_component,
        weights_used=result.weights_used,
    )
    db.add(opportunity_score)
    await db.commit()
    await db.refresh(opportunity_score)
    return opportunity_score
