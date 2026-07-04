"""add review columns and company share links

Revision ID: 9c4e1f8b27a3
Revises: 6d2f8a13c7e9
Create Date: 2026-07-04 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9c4e1f8b27a3'
down_revision: str | None = '6d2f8a13c7e9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 添削キュー：NULL = 教師未確認。既存行は全て未確認になるので、seed運用では
    # マイグレーション後に --reset で再seedする（seed が既読フラグを整える）。
    op.add_column('interview_evaluations',
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('interview_evaluations',
    sa.Column('reviewer_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_interview_evaluations_reviewer_id_users'),
                          'interview_evaluations', 'users', ['reviewer_id'], ['id'])
    op.create_table('company_share_links',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.Column('token', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked', sa.Boolean(), nullable=False),
    sa.Column('view_log', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_company_share_links_org_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_company_share_links')),
    sa.UniqueConstraint('token', name=op.f('uq_company_share_links_token'))
    )
    op.create_index(op.f('ix_company_share_links_org_id'), 'company_share_links', ['org_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_company_share_links_org_id'), table_name='company_share_links')
    op.drop_table('company_share_links')
    op.drop_constraint(op.f('fk_interview_evaluations_reviewer_id_users'),
                       'interview_evaluations', type_='foreignkey')
    op.drop_column('interview_evaluations', 'reviewer_id')
    op.drop_column('interview_evaluations', 'reviewed_at')
