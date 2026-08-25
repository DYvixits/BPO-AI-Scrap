"""Entity Resolution — companies + entity_aliases tables, research_results.company_id

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-26

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "research_job_id",
            sa.Uuid(),
            sa.ForeignKey("research_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("primary_domain", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("match_confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_companies_organization_id", "companies", ["organization_id"])
    op.create_index("ix_companies_research_job_id", "companies", ["research_job_id"])
    op.create_index("ix_companies_primary_domain", "companies", ["primary_domain"])

    op.create_table(
        "entity_aliases",
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
        sa.Column("alias_type", sa.String(16), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_entity_aliases_organization_id", "entity_aliases", ["organization_id"])
    op.create_index("ix_entity_aliases_company_id", "entity_aliases", ["company_id"])

    op.add_column(
        "research_results",
        sa.Column(
            "company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
        ),
    )
    op.create_index("ix_research_results_company_id", "research_results", ["company_id"])

    # RLS (see SECURITY.md's "Tenant isolation" section and migration
    # 0002) — companies/entity_aliases carry the same organization_id-scoped
    # protection as the other per-job tables. FORCE so it applies even to
    # the schema-owning role, though see SECURITY.md's caveat: this only
    # means anything for a connection that isn't a superuser.
    for table in ("companies", "entity_aliases"):
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
    op.drop_index("ix_research_results_company_id", table_name="research_results")
    op.drop_constraint("research_results_company_id_fkey", "research_results", type_="foreignkey")
    op.drop_column("research_results", "company_id")

    op.drop_index("ix_entity_aliases_company_id", table_name="entity_aliases")
    op.drop_index("ix_entity_aliases_organization_id", table_name="entity_aliases")
    op.drop_table("entity_aliases")

    op.drop_index("ix_companies_primary_domain", table_name="companies")
    op.drop_index("ix_companies_research_job_id", table_name="companies")
    op.drop_index("ix_companies_organization_id", table_name="companies")
    op.drop_table("companies")
