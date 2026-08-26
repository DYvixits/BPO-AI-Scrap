import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.commercial_signal import CommercialSignal
    from app.models.verification import ConfidenceScore, Evidence


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A resolved real-world company entity within one research job — the
    output of engines/entity_resolution: multiple crawled pages (e.g. a
    company's own site plus its Crunchbase profile, discovered via
    different search hits) that the resolver judged to be the same company
    get grouped under one Company row here, instead of surfacing as N
    disconnected, unrelated results (AUDIT_BPO_CRM.md Phase 5).
    """

    __tablename__ = "companies"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    research_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    primary_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Disclosed heuristic (engines/entity_resolution/resolver.py) — 1.0 for
    # a single-domain company (nothing to disambiguate), lower when pages
    # from different domains were merged on a name match alone. Not a
    # verified claim; see SECURITY.md on never fabricating confidence.
    match_confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    aliases: Mapped[list["EntityAlias"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    # engines/verification (AUDIT_BPO_CRM.md Phase 6) — populated once,
    # after entity resolution, alongside aliases above. No back_populates:
    # nothing in app/models/verification.py needs to navigate back to
    # Company, so this stays one-directional like the aliases relationship
    # would if EntityAlias didn't already need the reverse for its own code.
    evidence: Mapped[list["Evidence"]] = relationship(cascade="all, delete-orphan")
    confidence_score: Mapped["ConfidenceScore | None"] = relationship(
        uselist=False, cascade="all, delete-orphan"
    )
    # engines/commercial_signals (AUDIT_BPO_CRM.md Phase 7) — same
    # one-directional, populated-once-after-resolution lifecycle as
    # evidence/confidence_score above.
    signals: Mapped[list["CommercialSignal"]] = relationship(cascade="all, delete-orphan")


class EntityAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One literal name or domain variant found for a company, and which
    page it came from — the resolver's explainability trail: why were
    these pages grouped together?"""

    __tablename__ = "entity_aliases"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    alias_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "name" | "domain"
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="aliases")
