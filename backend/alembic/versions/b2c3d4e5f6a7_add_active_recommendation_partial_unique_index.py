"""add_active_recommendation_partial_unique_index

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-14 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create partial unique index for active recommendations on (finding_id, category)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    indexes = {idx['name'] for idx in insp.get_indexes('operational_recommendations')}
    if 'uq_active_rec_finding_category' not in indexes:
        op.create_index(
            'uq_active_rec_finding_category',
            'operational_recommendations',
            ['finding_id', 'category'],
            unique=True,
            postgresql_where=sa.text("status IN ('OPEN', 'IN_PROGRESS')"),
            sqlite_where=sa.text("status IN ('OPEN', 'IN_PROGRESS')"),
        )


def downgrade() -> None:
    """Drop partial unique index for active recommendations."""
    op.drop_index('uq_active_rec_finding_category', table_name='operational_recommendations')

