"""add notifications table

Revision ID: c3f1a8b2e4d9
Revises: 47e4e9424568
Create Date: 2026-10-16 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'c3f1a8b2e4d9'
down_revision = '47e4e9424568'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('resident_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column('body', sa.String(length=255), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.Column('related_type', sa.String(length=50), nullable=True),
        sa.Column('related_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['resident_id'], ['residents.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notifications_resident_id', 'notifications', ['resident_id'])
    op.create_index('ix_notifications_is_read', 'notifications', ['is_read'])


def downgrade():
    op.drop_index('ix_notifications_is_read', table_name='notifications')
    op.drop_index('ix_notifications_resident_id', table_name='notifications')
    op.drop_table('notifications')
