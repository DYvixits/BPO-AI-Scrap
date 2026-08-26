import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.engines.commercial_signals.detector import CommercialSignalType
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class CommercialSignal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One keyword-matched commercial event found on a company's crawled
    page (engines/commercial_signals) — funding, hiring, a leadership
    change, and so on. See that engine's module docstring for the
    disclosed keyword vocabulary (shared with Query Intelligence) and the
    time-decay approach behind `decayed_strength`."""

    __tablename__ = "commercial_signals"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    research_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    signal_type: Mapped[CommercialSignalType] = mapped_column(
        pg_enum(CommercialSignalType, "commercial_signal_type"), nullable=False, index=True
    )
    polarity: Mapped[str] = mapped_column(String(16), nullable=False)  # "positive" | "negative"
    matched_keyword: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    base_weight: Mapped[float] = mapped_column(Float, nullable=False)
    # Copied from the source crawl_pages row at detection time — the time
    # anchor decay is computed from, since no real event date is
    # extracted from the page text (see detector.py's module docstring).
    crawled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decayed_strength: Mapped[float] = mapped_column(Float, nullable=False)
