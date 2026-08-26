"""Fit + Intent + Opportunity Scoring — fit_scores, intent_scores,
opportunity_scores tables

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-26

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fit_scores",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "research_job_id",
            sa.Uuid(),
            sa.ForeignKey("research_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("matched_factors", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("unmatched_factors", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_fit_scores_organization_id", "fit_scores", ["organization_id"])
    op.create_index("ix_fit_scores_company_id", "fit_scores", ["company_id"])
    op.create_index("ix_fit_scores_research_job_id", "fit_scores", ["research_job_id"])

    op.create_table(
        "intent_scores",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "research_job_id",
            sa.Uuid(),
            sa.ForeignKey("research_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("contributing_signals", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_intent_scores_organization_id", "intent_scores", ["organization_id"])
    op.create_index("ix_intent_scores_company_id", "intent_scores", ["company_id"])
    op.create_index("ix_intent_scores_research_job_id", "intent_scores", ["research_job_id"])

    op.create_table(
        "opportunity_scores",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "research_job_id",
            sa.Uuid(),
            sa.ForeignKey("research_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "fit_score_id", sa.Uuid(), sa.ForeignKey("fit_scores.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "intent_score_id",
            sa.Uuid(),
            sa.ForeignKey("intent_scores.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "confidence_score_id",
            sa.Uuid(),
            sa.ForeignKey("confidence_scores.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("fit_component", sa.Float(), nullable=False),
        sa.Column("intent_component", sa.Float(), nullable=False),
        sa.Column("confidence_component", sa.Float(), nullable=False),
        sa.Column("freshness_component", sa.Float(), nullable=False),
        sa.Column("momentum_component", sa.Float(), nullable=False),
        sa.Column("weights_used", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_opportunity_scores_organization_id", "opportunity_scores", ["organization_id"]
    )
    op.create_index("ix_opportunity_scores_company_id", "opportunity_scores", ["company_id"])
    op.create_index(
        "ix_opportunity_scores_research_job_id", "opportunity_scores", ["research_job_id"]
    )

    # RLS (see SECURITY.md's "Tenant isolation" section and migrations
    # 0002/0005/0006/0007) — same tenant_isolation policy pattern as every
    # other per-job table.
    for table in ("fit_scores", "intent_scores", "opportunity_scores"):
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
    op.drop_index("ix_opportunity_scores_research_job_id", table_name="opportunity_scores")
    op.drop_index("ix_opportunity_scores_company_id", table_name="opportunity_scores")
    op.drop_index("ix_opportunity_scores_organization_id", table_name="opportunity_scores")
    op.drop_table("opportunity_scores")

    op.drop_index("ix_intent_scores_research_job_id", table_name="intent_scores")
    op.drop_index("ix_intent_scores_company_id", table_name="intent_scores")
    op.drop_index("ix_intent_scores_organization_id", table_name="intent_scores")
    op.drop_table("intent_scores")

    op.drop_index("ix_fit_scores_research_job_id", table_name="fit_scores")
    op.drop_index("ix_fit_scores_company_id", table_name="fit_scores")
    op.drop_index("ix_fit_scores_organization_id", table_name="fit_scores")
    op.drop_table("fit_scores")
