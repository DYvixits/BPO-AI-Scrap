import uuid

from sqlalchemy import JSON, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class FitScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The Fit Scoring Engine's output for one resolved Company — one row
    per company. See engines/fit_scoring/engine.py::compute_fit for what
    `score` means and why it's nullable (nothing to check fit against for
    a fully generic query)."""

    __tablename__ = "fit_scores"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False, unique=True
    )
    research_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_factors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    unmatched_factors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class IntentScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The Intent Scoring Engine's output for one resolved Company — one
    row per company. See engines/intent_scoring/engine.py::compute_intent
    for exactly what `score` aggregates."""

    __tablename__ = "intent_scores"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False, unique=True
    )
    research_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    contributing_signals: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class OpportunityScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The Opportunity Scoring Engine's output for one resolved Company —
    master spec §4's OPPORTUNITY = f(FIT, INTENT, CONFIDENCE, FRESHNESS,
    MOMENTUM). See engines/opportunity_scoring/engine.py::compute_
    opportunity for the (currently fixed, not per-tenant-configurable)
    weighting function and what `momentum` actually measures here."""

    __tablename__ = "opportunity_scores"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False, unique=True
    )
    research_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    fit_score_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fit_scores.id", ondelete="CASCADE"), nullable=False
    )
    intent_score_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("intent_scores.id", ondelete="CASCADE"), nullable=False
    )
    confidence_score_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("confidence_scores.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    fit_component: Mapped[float] = mapped_column(Float, nullable=False)
    intent_component: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_component: Mapped[float] = mapped_column(Float, nullable=False)
    freshness_component: Mapped[float] = mapped_column(Float, nullable=False)
    momentum_component: Mapped[float] = mapped_column(Float, nullable=False)
    weights_used: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
