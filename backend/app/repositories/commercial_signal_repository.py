import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.commercial_signals.detector import CommercialSignalType
from app.models.commercial_signal import CommercialSignal


async def add_signal(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    signal_type: CommercialSignalType,
    polarity: str,
    matched_keyword: str,
    excerpt: str,
    source_url: str,
    base_weight: float,
    crawled_at: datetime,
    decayed_strength: float,
) -> CommercialSignal:
    signal = CommercialSignal(
        organization_id=organization_id,
        company_id=company_id,
        research_job_id=job_id,
        signal_type=signal_type,
        polarity=polarity,
        matched_keyword=matched_keyword,
        excerpt=excerpt,
        source_url=source_url,
        base_weight=base_weight,
        crawled_at=crawled_at,
        decayed_strength=decayed_strength,
    )
    db.add(signal)
    await db.commit()
    await db.refresh(signal)
    return signal
