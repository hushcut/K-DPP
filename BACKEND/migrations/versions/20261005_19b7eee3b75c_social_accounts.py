"""social accounts — 카카오 로그인(DECISIONS 152·153)

- users.email·password_hash 를 비울 수 있게 한다(카카오 계정은 둘 다 없음). CHECK 로 둘은 같이
  있거나 같이 없게 한다 — 이메일만 있는 행이 생기면 이메일 로그인·비밀번호 찾기가 비밀번호 없는
  행을 만난다. 지금 행은 모두 이메일 계정(둘 다 있음)이라 CHECK 를 바로 걸 수 있다.
- social_accounts: (provider, subject) → user_id. UNIQUE 둘 — 한 소셜 계정은 한 사용자에게만,
  한 사용자는 제공자마다 하나만. user_id 로 시작하는 UNIQUE 가 user_id 조회의 색인을 겸한다.
  외래 키에 ON DELETE 가 없는 것은 기준선과 같다(탈퇴는 앱이 지운다 — main.py withdraw).
- downgrade: 이메일이 없는 사용자(카카오 계정)가 있으면 멈춘다. NOT NULL 로 되돌리려면 그 계정과
  토큰·이력을 지워야 하는데, 그건 사람이 정할 일이라 리비전이 대신 지우지 않는다.

Revision ID: 19b7eee3b75c
Revises: 09f14728ed0b
Create Date: 2026-10-05 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19b7eee3b75c'
down_revision: Union[str, Sequence[str], None] = '09f14728ed0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# database.User 의 CheckConstraint(name="email_password_together") 가 이름 규칙(ck_<표>_<이름>)으로 받는 이름.
CHECK_NAME = 'ck_users_email_password_together'


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('users', 'email', existing_type=sa.String(), nullable=True)
    op.alter_column('users', 'password_hash', existing_type=sa.String(), nullable=True)
    op.create_check_constraint(
        op.f(CHECK_NAME), 'users', '(email IS NULL) = (password_hash IS NULL)'
    )
    op.create_table('social_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(), nullable=False),
    sa.Column('subject', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_social_accounts_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_social_accounts')),
    sa.UniqueConstraint('provider', 'subject', name='uq_social_accounts_provider_subject'),
    sa.UniqueConstraint('user_id', 'provider', name='uq_social_accounts_user_id_provider')
    )


def downgrade() -> None:
    """Downgrade schema."""
    if not context.is_offline_mode():
        social_users = op.get_bind().execute(
            sa.text('SELECT count(*) FROM users WHERE email IS NULL')
        ).scalar()
        if social_users:
            raise RuntimeError(
                f'이메일이 없는 사용자(카카오 계정) {social_users}명이 있어 되돌리지 않습니다. '
                'users.email·password_hash 를 다시 NOT NULL 로 하려면 그 계정을 먼저 정리해야 합니다.'
            )
    op.drop_table('social_accounts')
    op.drop_constraint(op.f(CHECK_NAME), 'users', type_='check')
    op.alter_column('users', 'password_hash', existing_type=sa.String(), nullable=False)
    op.alter_column('users', 'email', existing_type=sa.String(), nullable=False)
