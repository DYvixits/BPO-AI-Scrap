"""initial schema — organizations, users, research pipeline tables

Revision ID: 0001
Revises:
Create Date: 2026-08-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# create_type=False: these types are created/dropped explicitly (once) in
# upgrade()/downgrade() below via .create()/.drop(). Without create_type=False,
# SQLAlchemy *also* auto-creates the enum type the first time a column of
# this type is included in a create_table() call — duplicating the explicit
# .create() call and raising DuplicateObjectError on a real Postgres target.
role_enum = postgresql.ENUM(
    "super_admin",
    "admin",
    "research_manager",
    "researcher",
    "analyst",
    "viewer",
    "api_client",
    name="role",
    create_type=False,
)
research_status_enum = postgresql.ENUM(
    "created",
    "queued",
    "searching",
    "crawling",
    "extracting",
    "completed",
    "failed",
    name="research_status",
    create_type=False,
)
research_mode_enum = postgresql.ENUM(
    "quick",
    "balanced",
    "deep",
    "verified",
    "investigation",
    "custom",
    name="research_mode",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    role_enum.create(bind, checkfirst=True)
    research_status_enum.create(bind, checkfirst=True)
    research_mode_enum.create(bind, checkfirst=True)

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "organization_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", role_enum, nullable=False, server_default="researcher"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )
    op.create_index("ix_organization_members_organization_id", "organization_members", ["organization_id"])
    op.create_index("ix_organization_members_user_id", "organization_members", ["user_id"])

    op.create_table(
        "research_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("status", research_status_enum, nullable=False, server_default="created"),
        sa.Column("mode", research_mode_enum, nullable=False, server_default="balanced"),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_research_jobs_organization_id", "research_jobs", ["organization_id"])
    op.create_index("ix_research_jobs_status", "research_jobs", ["status"])

    op.create_table(
        "research_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "research_job_id",
            sa.Uuid(),
            sa.ForeignKey("research_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_research_events_research_job_id", "research_events", ["research_job_id"])

    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "research_job_id",
            sa.Uuid(),
            sa.ForeignKey("research_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="discovered"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sources_research_job_id", "sources", ["research_job_id"])
    op.create_index("ix_sources_domain", "sources", ["domain"])

    op.create_table(
        "crawl_pages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_crawl_pages_source_id", "crawl_pages", ["source_id"])
    op.create_index("ix_crawl_pages_content_hash", "crawl_pages", ["content_hash"])

    op.create_table(
        "research_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "research_job_id",
            sa.Uuid(),
            sa.ForeignKey("research_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "crawl_page_id", sa.Uuid(), sa.ForeignKey("crawl_pages.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_research_results_research_job_id", "research_results", ["research_job_id"])


def downgrade() -> None:
    op.drop_table("research_results")
    op.drop_table("crawl_pages")
    op.drop_table("sources")
    op.drop_table("research_events")
    op.drop_table("research_jobs")
    op.drop_table("organization_members")
    op.drop_table("users")
    op.drop_table("organizations")

    bind = op.get_bind()
    research_mode_enum.drop(bind, checkfirst=True)
    research_status_enum.drop(bind, checkfirst=True)
    role_enum.drop(bind, checkfirst=True)
