"""Commercial Signal Engine — commercial_signals table

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# create_type=False: see migration 0001's comment. Values must stay in
# sync with app/engines/query_intelligence/keywords.py::SIGNALS' keys —
# see app/engines/commercial_signals/detector.py::CommercialSignalType.
commercial_signal_type_enum = postgresql.ENUM(
    "hiring",
    "expansion",
    "funding",
    "acquisition",
    "leadership_change",
    "product_launch",
    "digital_transformation",
    "layoffs",
    "closure",
    name="commercial_signal_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    commercial_signal_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "commercial_signals",
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
        sa.Column(
            "research_job_id",
            sa.Uuid(),
            sa.ForeignKey("research_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signal_type", commercial_signal_type_enum, nullable=False),
        sa.Column("polarity", sa.String(16), nullable=False),
        sa.Column("matched_keyword", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("base_weight", sa.Float(), nullable=False),
        sa.Column("crawled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decayed_strength", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_commercial_signals_organization_id", "commercial_signals", ["organization_id"])
    op.create_index("ix_commercial_signals_company_id", "commercial_signals", ["company_id"])
    op.create_index(
        "ix_commercial_signals_research_job_id", "commercial_signals", ["research_job_id"]
    )
    op.create_index("ix_commercial_signals_signal_type", "commercial_signals", ["signal_type"])

    # RLS (see SECURITY.md's "Tenant isolation" section and migrations
    # 0002/0005/0006) — same tenant_isolation policy pattern as every
    # other per-job table.
    op.execute("ALTER TABLE commercial_signals ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE commercial_signals FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON commercial_signals
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_commercial_signals_signal_type", table_name="commercial_signals")
    op.drop_index("ix_commercial_signals_research_job_id", table_name="commercial_signals")
    op.drop_index("ix_commercial_signals_company_id", table_name="commercial_signals")
    op.drop_index("ix_commercial_signals_organization_id", table_name="commercial_signals")
    op.drop_table("commercial_signals")

    commercial_signal_type_enum.drop(op.get_bind(), checkfirst=True)
