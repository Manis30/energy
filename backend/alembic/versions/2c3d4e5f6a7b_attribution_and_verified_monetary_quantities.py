"""Attribution details and verified monetary savings migration.

Adds verified_monetary_savings_inr and attribution_details_json columns to
intervention_assessments table to support three independent ledger quantities:
1. Verified electricity savings (kWh)
2. Estimated avoided cost (INR)
3. Verified monetary savings (INR, strictly when tariff contract is approved)

Revision ID: 2c3d4e5f6a7b
Revises: 1a2b3c4d5e6f
Create Date: 2026-11-19 18:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c3d4e5f6a7b'
down_revision: Union[str, Sequence[str], None] = '1a2b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table('intervention_assessments'):
        columns = [c['name'] for c in insp.get_columns('intervention_assessments')]
        if 'verified_monetary_savings_inr' not in columns:
            op.add_column(
                'intervention_assessments',
                sa.Column('verified_monetary_savings_inr', sa.Float(), nullable=True),
            )
        if 'attribution_details_json' not in columns:
            op.add_column(
                'intervention_assessments',
                sa.Column('attribution_details_json', sa.Text(), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table('intervention_assessments'):
        columns = [c['name'] for c in insp.get_columns('intervention_assessments')]
        if 'attribution_details_json' in columns:
            op.drop_column('intervention_assessments', 'attribution_details_json')
        if 'verified_monetary_savings_inr' in columns:
            op.drop_column('intervention_assessments', 'verified_monetary_savings_inr')
