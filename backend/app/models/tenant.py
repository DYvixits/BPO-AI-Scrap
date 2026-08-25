import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TenantTier(StrEnum):
    STANDARD = "standard"
    PRO = "pro"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class TenantQuota(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-organization resource limits (master spec §37/§38 — 'fair resource
    scheduling', 'a tenant should never be able to monopolize resources').

    Seeded from `default_quotas_for_tier()` (app/services/tenant_quotas.py)
    when an organization is created, then stored as ordinary editable rows —
    this is the Configuration Engine pattern (§56): nothing about a tenant's
    actual limits is hardcoded once the row exists, only the *defaults* for
    a fresh org are.
    """

    __tablename__ = "tenant_quotas"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )

    crawl_concurrency: Mapped[int] = mapped_column(Integer, nullable=False)
    max_concurrent_research_jobs: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_budget_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_mb_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_priority: Mapped[int] = mapped_column(Integer, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="quota")  # noqa: F821
