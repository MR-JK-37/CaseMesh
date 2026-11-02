"""phase6_dashboard_search_reports

Revision ID: af10d876b4e8
Revises: e87b9e0e2409
Create Date: 2026-10-29 15:04:00.506445

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'af10d876b4e8'
down_revision: str | Sequence[str] | None = 'e87b9e0e2409'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('saved_views',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )

    # Personal, per-user convenience data — every query is already
    # filtered by `owner_id == principal.user_id` at the application
    # layer (same pattern as `app/routers/sessions.py`'s own-session
    # list), so no RLS policy is added here; this mirrors that table's
    # precedent rather than inventing a second enforcement mechanism
    # for data this low-stakes (named filter sets, nothing sensitive).
    op.execute("GRANT SELECT, INSERT, DELETE ON saved_views TO icm_app")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('saved_views')
