"""add conversation turns

Revision ID: 4b7d2c91e0aa
Revises: df085a7ad5ed
Create Date: 2026-07-02 15:20:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4b7d2c91e0aa'
down_revision: str | None = 'df085a7ad5ed'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('conversation_turns',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('role', sa.Enum('partner', 'student', name='conversation_role', native_enum=False, length=32), nullable=False),
    sa.Column('text_ja', sa.Text(), nullable=False),
    sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['conversation_sessions.id'], name=op.f('fk_conversation_turns_session_id_conversation_sessions')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversation_turns')),
    sa.UniqueConstraint('session_id', 'seq', name=op.f('uq_conversation_turns_session_id'))
    )
    op.create_index(op.f('ix_conversation_turns_session_id'), 'conversation_turns', ['session_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_conversation_turns_session_id'), table_name='conversation_turns')
    op.drop_table('conversation_turns')
