import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.engines.verification.engine import TruthStatus
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class Evidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One crawled page counted as evidence for a resolved Company's
    confidence score (engines/verification) — the auditable trail behind
    the score: which page, which domain, what text was actually found
    there. Not a claim-level record (see engines/verification/engine.py's
    module docstring for why)."""

    __tablename__ = "evidence"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConfidenceScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The Verification Engine's output for one resolved Company — one row
    per company, computed once after Entity Resolution. See
    engines/verification/engine.py::compute_confidence for exactly what
    each field means and, just as important, what it doesn't (no claim-
    level agreement/contradiction detection yet — `status` is one of 5 of
    the master spec's 7 Truth Engine states, not all 7)."""

    __tablename__ = "confidence_scores"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False, unique=True
    )
    status: Mapped[TruthStatus] = mapped_column(
        pg_enum(TruthStatus, "truth_status"), nullable=False
    )
    source_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_diversity: Mapped[int] = mapped_column(Integer, nullable=False)
    freshness_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_completeness: Mapped[float] = mapped_column(Float, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
