import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class ResearchStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    SEARCHING = "searching"
    CRAWLING = "crawling"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"


class ResearchMode(StrEnum):
    QUICK = "quick"
    BALANCED = "balanced"
    DEEP = "deep"
    VERIFIED = "verified"
    INVESTIGATION = "investigation"
    CUSTOM = "custom"


class ResearchJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "research_jobs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    query: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ResearchStatus] = mapped_column(
        pg_enum(ResearchStatus, "research_status"),
        default=ResearchStatus.CREATED,
        nullable=False,
        index=True,
    )
    mode: Mapped[ResearchMode] = mapped_column(
        pg_enum(ResearchMode, "research_mode"), default=ResearchMode.BALANCED, nullable=False
    )
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # The structured plan the Query Intelligence Engine parsed the NL query
    # into (app/engines/query_intelligence) — a serialized ResearchObjective.
    # Populated once at job creation, never mutated afterward.
    objective: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    events: Mapped[list["ResearchEvent"]] = relationship(
        back_populates="research_job",
        cascade="all, delete-orphan",
        order_by="ResearchEvent.created_at",
    )
    sources: Mapped[list["Source"]] = relationship(
        back_populates="research_job", cascade="all, delete-orphan"
    )
    results: Mapped[list["ResearchResult"]] = relationship(
        back_populates="research_job", cascade="all, delete-orphan"
    )


class ResearchEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only progress log; also published on Redis pub/sub for the live UI."""

    __tablename__ = "research_events"

    # organization_id is denormalized onto every tenant-scoped table (rather
    # than only living on research_jobs and requiring a join) so that (a)
    # PostgreSQL RLS policies here are a plain equality check, not a
    # subquery, and (b) tenant-filtered queries can use a direct index
    # instead of joining through research_jobs. See docs/AUDIT_BPO_CRM.md §5.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    research_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    research_job: Mapped["ResearchJob"] = relationship(back_populates="events")


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sources"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    research_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="discovered", nullable=False)

    research_job: Mapped["ResearchJob"] = relationship(back_populates="sources")
    pages: Mapped[list["CrawlPage"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class CrawlPage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crawl_pages"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True, nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Second extraction pass output (engines/extraction/structured.py):
    # JSON-LD, Open Graph tags, emails/phones found in the page text.
    structured_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped["Source"] = relationship(back_populates="pages")


class ResearchResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "research_results"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    research_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    crawl_page_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_pages.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)

    research_job: Mapped["ResearchJob"] = relationship(back_populates="results")
