"""tenant hardening — tiers, quotas, denormalized organization_id, RLS

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-25

Adds (master spec §36-38, AUDIT_BPO_CRM.md §5):
  - organizations.tier + tenant_quotas (fair resource scheduling)
  - organization_id denormalized onto research_events/sources/crawl_pages/
    research_results, backfilled from research_jobs (via sources for
    crawl_pages)
  - PostgreSQL Row-Level Security on those four tables + tenant_quotas,
    enforced even for the owning role via FORCE ROW LEVEL SECURITY (the app
    connects as a normal, non-superuser role, so FORCE is sufficient here —
    see docs/AUDIT_BPO_CRM.md §5 and app/core/database.py for why
    research_jobs itself is deliberately NOT included: the worker's first
    read of a job by id has no tenant context to authenticate with yet,
    a bootstrapping problem, not an oversight).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

tenant_tier_enum = postgresql.ENUM(
    "standard", "pro", "business", "enterprise", name="tenant_tier", create_type=False
)

_RLS_TABLES = ["research_events", "sources", "crawl_pages", "research_results", "tenant_quotas"]


def upgrade() -> None:
    bind = op.get_bind()
    tenant_tier_enum.create(bind, checkfirst=True)

    # --- tiers & quotas ---
    op.add_column(
        "organizations",
        sa.Column("tier", tenant_tier_enum, nullable=False, server_default="standard"),
    )

    op.create_table(
        "tenant_quotas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("crawl_concurrency", sa.Integer(), nullable=False),
        sa.Column("max_concurrent_research_jobs", sa.Integer(), nullable=False),
        sa.Column("ai_budget_cents", sa.Integer(), nullable=False),
        sa.Column("storage_mb_limit", sa.Integer(), nullable=False),
        sa.Column("worker_priority", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id"),
    )
    op.create_index("ix_tenant_quotas_organization_id", "tenant_quotas", ["organization_id"])

    # Backfill a default (standard-tier) quota row for every organization
    # that existed before this migration — new orgs get one at signup time
    # (app/repositories/auth_repository.py), but pre-existing ones need a
    # one-time row here so quota checks never see "no row" as "unlimited."
    op.execute(
        """
        INSERT INTO tenant_quotas
            (id, organization_id, crawl_concurrency, max_concurrent_research_jobs,
             ai_budget_cents, storage_mb_limit, worker_priority)
        SELECT gen_random_uuid(), id, 4, 2, 0, 500, 1
        FROM organizations
        """
    )

    # --- denormalize organization_id onto the four child tables ---
    op.add_column("research_events", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.execute(
        """
        UPDATE research_events e
        SET organization_id = j.organization_id
        FROM research_jobs j
        WHERE e.research_job_id = j.id
        """
    )
    op.alter_column("research_events", "organization_id", nullable=False)
    op.create_foreign_key(
        "fk_research_events_organization_id",
        "research_events",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_research_events_organization_id", "research_events", ["organization_id"])

    op.add_column("sources", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.execute(
        """
        UPDATE sources s
        SET organization_id = j.organization_id
        FROM research_jobs j
        WHERE s.research_job_id = j.id
        """
    )
    op.alter_column("sources", "organization_id", nullable=False)
    op.create_foreign_key(
        "fk_sources_organization_id", "sources", "organizations", ["organization_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_sources_organization_id", "sources", ["organization_id"])

    op.add_column("crawl_pages", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.execute(
        """
        UPDATE crawl_pages p
        SET organization_id = s.organization_id
        FROM sources s
        WHERE p.source_id = s.id
        """
    )
    op.alter_column("crawl_pages", "organization_id", nullable=False)
    op.create_foreign_key(
        "fk_crawl_pages_organization_id",
        "crawl_pages",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_crawl_pages_organization_id", "crawl_pages", ["organization_id"])

    op.add_column("research_results", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.execute(
        """
        UPDATE research_results r
        SET organization_id = j.organization_id
        FROM research_jobs j
        WHERE r.research_job_id = j.id
        """
    )
    op.alter_column("research_results", "organization_id", nullable=False)
    op.create_foreign_key(
        "fk_research_results_organization_id",
        "research_results",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_research_results_organization_id", "research_results", ["organization_id"])

    # --- Row-Level Security ---
    #
    # NULLIF(..., '') matters and is not defensive-programming decoration:
    # current_setting('app.current_tenant', true) returns NULL only the
    # first time a session touches this (undeclared, session-scoped) custom
    # GUC. Once *any* transaction on that connection has done `SET LOCAL
    # app.current_tenant = ...`, later transactions on the same pooled
    # connection that don't set it again get '' back, not NULL — and
    # ''::uuid raises a hard error rather than evaluating the policy to
    # false. Wrapping in NULLIF converts that '' to NULL before the cast, so
    # "tenant context not set on this transaction" always fails closed
    # (no rows visible) instead of sometimes raising, depending on what the
    # pooled connection happened to be used for previously. Verified live
    # against PostgreSQL — see tests/test_rls.py.
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            """
        )


def downgrade() -> None:
    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_research_results_organization_id", table_name="research_results")
    op.drop_constraint("fk_research_results_organization_id", "research_results", type_="foreignkey")
    op.drop_column("research_results", "organization_id")

    op.drop_index("ix_crawl_pages_organization_id", table_name="crawl_pages")
    op.drop_constraint("fk_crawl_pages_organization_id", "crawl_pages", type_="foreignkey")
    op.drop_column("crawl_pages", "organization_id")

    op.drop_index("ix_sources_organization_id", table_name="sources")
    op.drop_constraint("fk_sources_organization_id", "sources", type_="foreignkey")
    op.drop_column("sources", "organization_id")

    op.drop_index("ix_research_events_organization_id", table_name="research_events")
    op.drop_constraint("fk_research_events_organization_id", "research_events", type_="foreignkey")
    op.drop_column("research_events", "organization_id")

    op.drop_index("ix_tenant_quotas_organization_id", table_name="tenant_quotas")
    op.drop_table("tenant_quotas")

    op.drop_column("organizations", "tier")

    bind = op.get_bind()
    tenant_tier_enum.drop(bind, checkfirst=True)
