"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2024-01-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sources table
    op.create_table(
        'sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('url', sa.String(500), nullable=False),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('source_type', sa.String(50), nullable=True),
        sa.Column('last_checked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url')
    )

    # Episodes table
    op.create_table(
        'episodes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=True),
        sa.Column('unique_id', sa.String(200), nullable=False),
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('url', sa.String(500), nullable=True),
        sa.Column('audio_url', sa.String(500), nullable=True),
        sa.Column('transcript', sa.Text(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', name='episodestatus'), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('unique_id')
    )

    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(200), nullable=True),
        sa.Column('telegram_chat_id', sa.String(100), nullable=True),
        sa.Column('preferred_digest_time', sa.String(5), nullable=True),
        sa.Column('timezone', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('telegram_chat_id')
    )

    # Subscriptions table
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('source_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Daily digest queue table
    op.create_table(
        'daily_digest_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('episode_id', sa.Integer(), nullable=True),
        sa.Column('date_added', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['episode_id'], ['episodes.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Indexes for common queries
    op.create_index('ix_episodes_status', 'episodes', ['status'])
    op.create_index('ix_episodes_source_id', 'episodes', ['source_id'])
    op.create_index('ix_subscriptions_user_id', 'subscriptions', ['user_id'])
    op.create_index('ix_subscriptions_source_id', 'subscriptions', ['source_id'])
    op.create_index('ix_daily_digest_queue_user_id', 'daily_digest_queue', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_daily_digest_queue_user_id')
    op.drop_index('ix_subscriptions_source_id')
    op.drop_index('ix_subscriptions_user_id')
    op.drop_index('ix_episodes_source_id')
    op.drop_index('ix_episodes_status')
    op.drop_table('daily_digest_queue')
    op.drop_table('subscriptions')
    op.drop_table('users')
    op.drop_table('episodes')
    op.drop_table('sources')
    op.execute('DROP TYPE episodestatus')
