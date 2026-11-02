"""closet snapshots — 옷장 서버 백업(DECISIONS 100·242)

- closet_snapshots: 사용자당 한 행(user_id 가 PK 이자 users.id 외래 키). 앱이 만든 옷 JSON 배열을 서버가
  해석하지 않고 그대로 보관한다. version 은 첫 저장 1, 내용이 바뀔 때만 +1.
- items 는 Text 다. 같은 내용 비교를 글자로 하는데 JSONB 는 키 순서를 바꾸고 \\u0000 을 거부한다.
  JSON 을 Text 에 직렬화하는 기존 관례(analysis_results.materials 등)와도 같다.
- 외래 키에 ON DELETE 가 없는 것은 기준선과 같다(탈퇴는 앱이 지운다 — main.py delete_user_rows).
- CHECK 둘(version >= 1, item_count >= 0)은 alembic check 가 비교하지 않으므로 모델과 여기 양쪽에 손으로 적는다.
- downgrade: 백업 행이 있으면 멈춘다. 사용자 백업을 지울지는 사람이 정할 일이라 리비전이 대신 지우지 않는다.

Revision ID: a28c2a50b363
Revises: 19b7eee3b75c
Create Date: 2026-10-14 16:55:23.328586

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a28c2a50b363'
down_revision: Union[str, Sequence[str], None] = '19b7eee3b75c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('closet_snapshots',
    sa.Column('user_id', sa.Integer(), autoincrement=False, nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('item_count', sa.Integer(), nullable=False),
    sa.Column('items', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('version >= 1', name=op.f('ck_closet_snapshots_version_positive')),
    sa.CheckConstraint('item_count >= 0', name=op.f('ck_closet_snapshots_item_count_nonnegative')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_closet_snapshots_user_id_users')),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_closet_snapshots'))
    )


def downgrade() -> None:
    """Downgrade schema."""
    if not context.is_offline_mode():
        snapshots = op.get_bind().execute(
            sa.text('SELECT count(*) FROM closet_snapshots')
        ).scalar()
        if snapshots:
            raise RuntimeError(
                f'옷장 백업 {snapshots}개가 있어 되돌리지 않습니다. 사용자 백업을 지울지는 사람이 정합니다.'
            )
    op.drop_table('closet_snapshots')
