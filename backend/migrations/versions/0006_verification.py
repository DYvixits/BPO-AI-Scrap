"""Verification Engine — evidence + confidence_scores tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# create_type=False: see migration 0001's comment — the type is created/
# dropped explicitly below, once, not implicitly by create_table().
truth_status_enum = postgresql.ENUM(
    "unverifiable",
    "uncertain",
    "corroborated",
    "verified",
    "outdated",
    name="truth_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    truth_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_evidence_organization_id", "evidence", ["organization_id"])
    op.create_index("ix_evidence_company_id", "evidence", ["company_id"])

    op.create_table(
        "confidence_scores",
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
        sa.Column("status", truth_status_enum, nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("source_diversity", sa.Integer(), nullable=False),
        sa.Column("freshness_score", sa.Float(), nullable=False),
        sa.Column("evidence_completeness", sa.Float(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_confidence_scores_organization_id", "confidence_scores", ["organization_id"])
    op.create_index("ix_confidence_scores_company_id", "confidence_scores", ["company_id"])

    # RLS (see SECURITY.md's "Tenant isolation" section and migrations
    # 0002/0005) — same tenant_isolation policy pattern as every other
    # per-job table.
    for table in ("evidence", "confidence_scores"):
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
    op.drop_index("ix_confidence_scores_company_id", table_name="confidence_scores")
    op.drop_index("ix_confidence_scores_organization_id", table_name="confidence_scores")
    op.drop_table("confidence_scores")

    op.drop_index("ix_evidence_company_id", table_name="evidence")
    op.drop_index("ix_evidence_organization_id", table_name="evidence")
    op.drop_table("evidence")

    truth_status_enum.drop(op.get_bind(), checkfirst=True)
