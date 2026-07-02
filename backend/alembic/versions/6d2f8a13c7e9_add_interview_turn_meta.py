"""add interview turn meta

Revision ID: 6d2f8a13c7e9
Revises: 4b7d2c91e0aa
Create Date: 2026-07-02 18:40:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6d2f8a13c7e9'
down_revision: str | None = '4b7d2c91e0aa'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 既存行（seed の面接履歴）があるため server_default で埋める。
    op.add_column('interview_turns',
    sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
              server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    op.drop_column('interview_turns', 'meta')
