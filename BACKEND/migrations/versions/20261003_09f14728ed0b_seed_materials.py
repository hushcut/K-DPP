"""seed materials — 소재 22종(이 시점의 init_data.MATERIAL_SEEDS)

값을 init_data 에서 import 하지 않고 여기 적어 둔다. 한 번 적용된 리비전은 뜻이
바뀌면 안 되는데, import 하면 나중에 목록을 고칠 때 이 리비전의 결과까지 바뀐다.
소재·계수를 바꿀 때는 init_data.MATERIAL_SEEDS(프론트 사본 두 파일과 대조됨)를 고치고
새 리비전(UPDATE·INSERT)을 더한다 — 둘이 어긋나면 tests/test_migrations.py 가 실패한다.

Revision ID: 09f14728ed0b
Revises: 98b9938f3cd5
Create Date: 2026-10-03 21:18:52.430502

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '09f14728ed0b'
down_revision: Union[str, Sequence[str], None] = '98b9938f3cd5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UNIT = 'kg CO2eq/kg textile'

# (name_ko, name_en, aliases, carbon_factor) — 넣는 순서가 id 순서이고 /materials 가 id 순으로 보낸다.
MATERIALS = [
    ("면", "cotton", ["면", "코튼", "cotton", "COTTON"], 8.3),
    ("폴리에스터", "polyester", ["폴리에스터", "polyester", "POLYESTER", "poly"], 9.5),
    ("레이온", "rayon", ["레이온", "rayon", "RAYON"], 6.4),
    ("나일론", "nylon", ["나일론", "nylon", "NYLON", "polyamide"], 11.0),
    ("울", "wool", ["울", "모", "wool", "WOOL"], 13.9),
    ("아크릴", "acrylic", ["아크릴", "acrylic", "ACRYLIC", "polyacryl"], 10.0),
    ("스판덱스", "spandex", ["스판덱스", "엘라스테인", "spandex", "elastane", "lycra"], 12.0),
    ("린넨", "linen", ["린넨", "리넨", "마", "linen", "LINEN"], 4.5),
    ("비스코스", "viscose", ["비스코스", "viscose", "VISCOSE", "viskose"], 6.4),
    ("실크", "silk", ["실크", "견", "silk", "SILK"], 15.0),
    ("모달", "modal", ["모달", "modal", "MODAL"], 6.0),
    ("캐시미어", "cashmere", ["캐시미어", "cashmere", "CASHMERE", "kashmir"], 30.0),
    ("폴리우레탄", "polyurethane", ["폴리우레탄", "polyurethane", "PU", "pu"], 12.0),
    ("가죽", "leather", ["가죽", "leather", "LEATHER"], 20.0),
    ("라미", "ramie", ["라미", "ramie", "RAMIE"], 4.5),
    ("리오셀", "lyocell", ["리오셀", "텐셀", "lyocell", "tencel"], 5.5),
    ("다운", "down", ["다운", "우모", "오리솜털", "거위솜털", "down"], 18.0),
    ("깃털", "feather", ["깃털", "오리깃털", "거위깃털", "feather"], 12.0),
    ("야크", "yak", ["야크", "yak", "YAK"], 18.0),
    ("모헤어", "mohair", ["모헤어", "mohair", "MOHAIR"], 18.0),
    ("대나무", "bamboo", ["대나무", "bamboo", "BAMBOO"], 5.0),
    ("큐프로", "cupro", ["큐프로", "cupro", "CUPRO"], 6.0),
]

materials = sa.table(
    "materials",
    sa.column("name_ko", sa.String),
    sa.column("name_en", sa.String),
    sa.column("aliases", sa.Text),
    sa.column("carbon_factor", sa.Float),
    sa.column("unit", sa.String),
)


def upgrade() -> None:
    op.bulk_insert(
        materials,
        [
            {
                "name_ko": name_ko,
                "name_en": name_en,
                "aliases": json.dumps(aliases, ensure_ascii=False),
                "carbon_factor": carbon_factor,
                "unit": UNIT,
            }
            for name_ko, name_en, aliases, carbon_factor in MATERIALS
        ],
    )


def downgrade() -> None:
    op.execute(
        materials.delete().where(
            materials.c.name_en.in_([name_en for _, name_en, _, _ in MATERIALS])
        )
    )
