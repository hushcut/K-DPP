"""의류 무게표 계약: 앱 내장 표와 서버 표가 어긋나지 않는지 확인한다.

앱은 서버 `GET /clothing-types`(`main.py`의 `CLOTHING_TYPE_OPTIONS`)를 먼저 쓰고,
받지 못하면 `FRONTEND/lib/utils/clothing_type_catalog.dart`의 내장 표를 쓴다
(DECISIONS 2026-09-13 회의 ②). 탄소 계산은 앱이 보낸 최소·최대 무게로 하므로,
두 표가 다르면 **같은 옷이 네트워크 상태에 따라 다른 탄소값**으로 저장된다.

어느 한쪽 테스트로는 잡히지 않는다(서버는 자기 표만, 앱은 자기 표만 본다).
받은 서버 표는 기기에 저장하지 않으므로(DECISIONS 2026-09-16) 내장 표가 유일한 대체값이다.
"""

import re
from pathlib import Path

import pytest

import main
from test_material_name_contract import strip_dart_line_comments


REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "FRONTEND" / "lib" / "utils" / "clothing_type_catalog.dart"

_OPTION_BLOCK = re.compile(r"ClothingTypeOption\((.*?)\)\s*,", re.S)
_STRING_FIELD = r"{name}:\s*'([^']*)'"
_NUMBER_FIELD = r"{name}:\s*(\d+(?:\.\d+)?)"


def _field(block: str, pattern: str, name: str):
    match = re.search(pattern.format(name=name), block)
    return match.group(1) if match else None


def parse_catalog(source: str) -> list[dict]:
    """`options = [ ... ];` 안의 범위 항목만 읽는다. 직접 입력 자리 항목은 뺀다."""

    code = strip_dart_line_comments(source)
    start = code.find("options = [")
    end = code.find("];", start)

    if start == -1 or end == -1:
        return []

    items = []

    for block in _OPTION_BLOCK.findall(code[start:end]):
        if "isDirectWeightPlaceholder: true" in block:
            continue

        items.append(
            {
                "id": _field(block, _STRING_FIELD, "id"),
                "label": _field(block, _STRING_FIELD, "label"),
                "category": _field(block, _STRING_FIELD, "category"),
                "min_weight_grams": float(_field(block, _NUMBER_FIELD, "minWeightGram") or "nan"),
                "max_weight_grams": float(_field(block, _NUMBER_FIELD, "maxWeightGram") or "nan"),
                "estimated_weight_grams": float(
                    _field(block, _NUMBER_FIELD, "estimatedWeightGram") or "nan"
                ),
            }
        )

    return items


def load_frontend_catalog() -> list[dict]:
    if not CATALOG_PATH.exists():
        pytest.fail(
            f"앱 내장 무게표를 찾지 못했습니다: {CATALOG_PATH}. "
            "파일이 옮겨졌다면 이 테스트의 경로도 함께 고쳐야 합니다."
        )

    items = parse_catalog(CATALOG_PATH.read_text(encoding="utf-8"))

    if not items:
        pytest.fail("앱 내장 무게표가 비어 있거나 형식이 바뀌었습니다.")

    return items


def server_catalog() -> list[dict]:
    return [
        {**item, **{key: float(item[key]) for key in (
            "min_weight_grams", "max_weight_grams", "estimated_weight_grams"
        )}}
        for item in main.CLOTHING_TYPE_OPTIONS
    ]


def test_frontend_catalog_matches_server_in_order():
    """식별자·이름·분류·세 무게가 서버와 같고 순서도 같다.

    순서가 다르면 서버 표를 받기 전후로 선택창 목록 순서가 바뀐다.
    """

    frontend = load_frontend_catalog()
    server = server_catalog()

    assert [item["id"] for item in frontend] == [item["id"] for item in server], (
        "앱 내장 무게표와 서버 표의 종류·순서가 다릅니다."
    )

    mismatched = [
        (item["id"], key, item[key], expected[key])
        for item, expected in zip(frontend, server)
        for key in expected
        if item[key] != expected[key]
    ]

    assert not mismatched, (
        "앱 내장 무게표가 서버와 다릅니다 (종류, 항목, 앱, 서버): "
        f"{mismatched}. 서버를 받지 못한 기기에서 같은 옷이 다른 탄소값으로 저장됩니다."
    )


def test_parser_reads_every_field():
    """필드를 하나라도 못 읽으면 None·NaN이 되어 위 비교가 조용히 흔들린다."""

    for item in load_frontend_catalog():
        assert all(item[key] for key in ("id", "label", "category")), item
        assert all(
            item[key] == item[key]  # NaN 검사
            for key in ("min_weight_grams", "max_weight_grams", "estimated_weight_grams")
        ), item


def test_parser_ignores_commented_out_option():
    source = """
  static const List<ClothingTypeOption> options = [
    ClothingTypeOption(
      id: 'knit',
      label: '니트',
      category: '상의',
      minWeightGram: 400,
      maxWeightGram: 900,
      estimatedWeightGram: 620,
      icon: Icons.texture_outlined,
    ),
    // ClothingTypeOption(
    //   id: 'outer',
    // ),
  ];
"""

    assert [item["id"] for item in parse_catalog(source)] == ["knit"]
