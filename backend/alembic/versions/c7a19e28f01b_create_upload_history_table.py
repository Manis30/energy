"""create_upload_history_table

Revision ID: c7a19e28f01b
Revises: be415c420bad
Create Date: 2026-11-12 23:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7a19e28f01b'
down_revision: Union[str, Sequence[str], None] = 'be415c420bad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the upload_history table for daily report audit logging."""
    op.create_table(
        'upload_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('upload_id', sa.String(length=50), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('report_type', sa.String(length=50), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('file_format', sa.String(length=20), nullable=False),
        sa.Column('sheet_name', sa.String(length=100), nullable=True),
        sa.Column('reporting_date', sa.Date(), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('total_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('valid_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rejected_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duplicate_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('mode', sa.String(length=30), nullable=False),
        sa.Column('audit_details', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_upload_history'),
        sa.UniqueConstraint('upload_id', name='uq_upload_history_upload_id'),
    )
    op.create_index('idx_upload_history_upload_id', 'upload_history', ['upload_id'])
    op.create_index('idx_upload_history_reporting_date', 'upload_history', ['reporting_date'])
    op.create_index('idx_upload_history_report_type', 'upload_history', ['report_type'])
    op.create_index('idx_upload_history_uploaded_at', 'upload_history', ['uploaded_at'])


def downgrade() -> None:
    """Drop upload_history table and indexes."""
    op.drop_index('idx_upload_history_uploaded_at', table_name='upload_history')
    op.drop_index('idx_upload_history_report_type', table_name='upload_history')
    op.drop_index('idx_upload_history_reporting_date', table_name='upload_history')
    op.drop_index('idx_upload_history_upload_id', table_name='upload_history')
    op.drop_table('upload_history')

