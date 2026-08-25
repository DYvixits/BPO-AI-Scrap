"""crawl_pages.structured_data — the multi-pass extraction engine's second
pass output (JSON-LD, Open Graph, contact info)

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-25

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "crawl_pages",
        sa.Column("structured_data", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("crawl_pages", "structured_data")
