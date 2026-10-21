"""baseline develop schema — develop(cc5e44a) 표 4개, create_all 과 같은 스키마

autogenerate 결과를 손으로 검토했다(2026-10-03, 맥 — DECISIONS 110 2단계):
- 타입: String → VARCHAR(길이 제한 없음, 길이 검사는 앱), Float → double precision,
  DateTime → timestamp without time zone(앱이 UTC 를 시간대 없이 저장 — database.utc_now).
- 기본값: 모델의 default= 는 파이썬 쪽 값이라 DB 기본값은 없다. SQL 로 직접 넣는
  리비전은 NOT NULL 칸을 모두 채워야 한다.
- PK 칸의 index=True 때문에 PK 와 겹치는 인덱스(ix_*_id, ix_access_tokens_token)가
  생긴다. 기준선은 develop 모델과 같아야 해서 그대로 둔다.
- 외래 키에 ON DELETE 가 없다. 탈퇴는 앱이 토큰·이력을 먼저 지운다(main.py withdraw).
- 제약 이름은 database.NAMING_CONVENTION(pk_·fk_·ix_) — 이후 리비전이 이 이름으로 가리킨다.

Revision ID: 98b9938f3cd5
Revises: 
Create Date: 2026-10-03 21:18:20.434667

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '98b9938f3cd5'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('materials',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name_ko', sa.String(), nullable=False),
    sa.Column('name_en', sa.String(), nullable=False),
    sa.Column('aliases', sa.Text(), nullable=False),
    sa.Column('carbon_factor', sa.Float(), nullable=False),
    sa.Column('unit', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_materials'))
    )
    op.create_index(op.f('ix_materials_id'), 'materials', ['id'], unique=False)
    op.create_index(op.f('ix_materials_name_en'), 'materials', ['name_en'], unique=True)
    op.create_index(op.f('ix_materials_name_ko'), 'materials', ['name_ko'], unique=True)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('nickname', sa.String(), nullable=False),
    sa.Column('password_hash', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_table('access_tokens',
    sa.Column('token', sa.String(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_access_tokens_user_id_users')),
    sa.PrimaryKeyConstraint('token', name=op.f('pk_access_tokens'))
    )
    op.create_index(op.f('ix_access_tokens_token'), 'access_tokens', ['token'], unique=False)
    op.create_index(op.f('ix_access_tokens_user_id'), 'access_tokens', ['user_id'], unique=False)
    op.create_table('analysis_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('materials', sa.Text(), nullable=False),
    sa.Column('carbon_footprint', sa.Float(), nullable=False),
    sa.Column('carbon_footprint_min', sa.Float(), nullable=True),
    sa.Column('carbon_footprint_max', sa.Float(), nullable=True),
    sa.Column('min_weight_grams', sa.Float(), nullable=True),
    sa.Column('max_weight_grams', sa.Float(), nullable=True),
    sa.Column('unit', sa.String(), nullable=False),
    sa.Column('raw_ocr_text', sa.Text(), nullable=True),
    sa.Column('unknown_materials', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_analysis_results_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_analysis_results'))
    )
    op.create_index(op.f('ix_analysis_results_id'), 'analysis_results', ['id'], unique=False)
    op.create_index(op.f('ix_analysis_results_user_id'), 'analysis_results', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_analysis_results_user_id'), table_name='analysis_results')
    op.drop_index(op.f('ix_analysis_results_id'), table_name='analysis_results')
    op.drop_table('analysis_results')
    op.drop_index(op.f('ix_access_tokens_user_id'), table_name='access_tokens')
    op.drop_index(op.f('ix_access_tokens_token'), table_name='access_tokens')
    op.drop_table('access_tokens')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_materials_name_ko'), table_name='materials')
    op.drop_index(op.f('ix_materials_name_en'), table_name='materials')
    op.drop_index(op.f('ix_materials_id'), table_name='materials')
    op.drop_table('materials')
