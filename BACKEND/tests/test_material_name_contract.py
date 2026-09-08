"""소재 계층 계약: 서버 시드와 프론트 사본이 어긋나지 않는지 확인한다.

프론트 `FRONTEND/lib/utils/clothing_estimator.dart`는 서버 소재 표
(`init_data.py`의 `MATERIAL_SEEDS`)를 두 벌로 옮겨 갖고 있다.

1. `_standardNamesByAlias` — 한글명·별칭 → 영문 표준명
2. `_emissionFactorsByStandardName` — 영문 표준명 → carbon_factor

프론트가 이 사본을 갖는 이유는 저장 **전** 프리뷰 탄소값과, 옷장에 영구 저장되는
건강도를 서버 왕복 없이 계산하기 때문이다. 사본이 어긋나면 두 가지가 조용히 깨진다.

- 이름이 어긋나면: 스캔이 성공해도 서버가 내려준 한글 표시명('면')을 못 알아봐
  기본계수로 계산되고, 잘못된 건강도가 옷장에 남는다(탄소와 달리 건강도는 서버가
  덮어쓰지 않는다).
- 숫자가 어긋나면: 저장 전후로 같은 옷의 탄소값이 달라진다.

이 결함은 양쪽 어느 한 계층의 테스트로도 잡히지 않는다. 서버는 자기 시드만,
프론트는 자기 표만 보기 때문이다. 그래서 여기서 두 파일을 맞대어 본다.

※ 계수 숫자의 동기화는 **임시다.** 서버 시드의 `carbon_factor`는 그 파일 주석대로
개발용 추정값이고, 팀 승인 출처로 교체될 예정이다. 정본을 서버 한 곳에 두고
프론트가 `/materials`에서 받아 캐시하는 구조로 갈지는 미결(`NEXT_WORK.md` D08).
그때까지는 이 테스트가 두 사본을 붙들어 둔다.
"""

import re
from pathlib import Path

import pytest

import init_data


REPO_ROOT = Path(__file__).resolve().parents[2]
ESTIMATOR_PATH = REPO_ROOT / "FRONTEND" / "lib" / "utils" / "clothing_estimator.dart"

# `'면': 'cotton',` 꼴
_ALIAS_ENTRY = re.compile(r"'([^']+)'\s*:\s*'([^']+)'\s*,")
# `'cotton': 8.3,` 꼴
_FACTOR_ENTRY = re.compile(r"'([^']+)'\s*:\s*(\d+(?:\.\d+)?)\s*,")


def strip_dart_line_comments(source: str) -> str:
    """`//` 주석을 지운다. 작은따옴표 문자열 안의 `//`는 건드리지 않는다.

    주석을 남겨 두면 파서가 죽은 항목을 살아 있는 것으로 읽는다. 실제로
    `// '캐시미어': 'cashmere',` 처럼 한 줄만 주석 처리해도 6건이 전부 통과했다.
    표 항목 12개는 이 테스트가 유일한 방어선이라(프론트 계수가 기본계수와 같거나
    Dart 테스트가 그 항목을 참조하지 않는 경우) 그대로 두면 죽은 매핑이 초록으로 나간다.
    마커 탐색도 이 결과 위에서 하므로 문서 주석 안의 표 이름에 걸리지 않는다.
    """

    lines = []

    for line in source.splitlines():
        kept = []
        in_string = False
        index = 0

        while index < len(line):
            char = line[index]

            if in_string:
                kept.append(char)
                if char == "\\" and index + 1 < len(line):
                    kept.append(line[index + 1])
                    index += 2
                    continue
                if char == "'":
                    in_string = False
                index += 1
                continue

            if char == "'":
                in_string = True
                kept.append(char)
                index += 1
                continue

            if char == "/" and line[index + 1 : index + 2] == "/":
                break

            kept.append(char)
            index += 1

        lines.append("".join(kept))

    return "\n".join(lines)


def parse_dart_map(source: str, marker: str, pattern: re.Pattern):
    """주석을 걷어낸 Dart 소스에서 표 하나를 읽는다. 테스트가 직접 호출할 수 있게 분리했다."""

    code = strip_dart_line_comments(source)
    start = code.find(marker)

    if start == -1:
        return None

    end = code.find("};", start)

    if end == -1:
        return None

    return pattern.findall(code[start + len(marker) : end])


def _read_dart_map(marker: str, pattern: re.Pattern):
    if not ESTIMATOR_PATH.exists():
        pytest.fail(
            f"프론트 소재 표를 찾지 못했습니다: {ESTIMATOR_PATH}. "
            "모노레포 구조가 바뀌었다면 이 테스트의 경로도 함께 고쳐야 합니다."
        )

    entries = parse_dart_map(
        ESTIMATOR_PATH.read_text(encoding="utf-8"), marker, pattern
    )

    if entries is None:
        pytest.fail(
            f"{ESTIMATOR_PATH.name}에서 {marker!r} 표를 찾지 못했거나 표가 닫히지 않았습니다. "
            "이름이 바뀌었다면 이 테스트도 함께 고쳐야 합니다."
        )

    # 표가 통째로 주석 처리되면 빈 목록이 되는데, 그대로 두면 '누락 0건'으로 읽혀
    # 전건 통과한다. 로더에서 막아 개별 테스트의 방어에 기대지 않는다.
    if not entries:
        pytest.fail(
            f"{ESTIMATOR_PATH.name}의 {marker!r} 표가 비어 있습니다. "
            "표가 통째로 주석 처리됐거나 형식이 바뀌었습니다."
        )

    return entries


def load_frontend_alias_map() -> dict[str, str]:
    return {
        alias.strip().lower(): standard_name.strip().lower()
        for alias, standard_name in _read_dart_map(
            "_standardNamesByAlias = {", _ALIAS_ENTRY
        )
    }


def load_frontend_factor_map() -> dict[str, float]:
    return {
        name.strip().lower(): float(factor)
        for name, factor in _read_dart_map(
            "_emissionFactorsByStandardName = {", _FACTOR_ENTRY
        )
    }


def iter_seed_aliases():
    """(별칭, 영문 표준명) 쌍을 돌려준다. 영문 표준명 자체는 제외한다."""

    for seed in init_data.MATERIAL_SEEDS:
        name_en = seed["name_en"].strip().lower()

        for candidate in {seed["name_ko"], *seed["aliases"]}:
            alias = candidate.strip().lower()

            # 영문 표준명과 같은 별칭('cotton', 'COTTON')은 정규화만으로 맞으므로
            # 별칭 표에 없어도 된다.
            if alias == name_en:
                continue

            yield alias, name_en


def seed_factors() -> dict[str, float]:
    return {
        seed["name_en"].strip().lower(): float(seed["carbon_factor"])
        for seed in init_data.MATERIAL_SEEDS
    }


# --- 이름 대응 --------------------------------------------------------------


def test_frontend_alias_map_covers_every_server_alias():
    frontend_map = load_frontend_alias_map()
    assert frontend_map, "프론트 소재 별칭 표가 비어 있습니다."

    missing = sorted(
        {alias for alias, _ in iter_seed_aliases() if alias not in frontend_map}
    )

    assert not missing, (
        "서버 시드에는 있으나 프론트 ClothingEstimator가 모르는 소재 이름입니다: "
        f"{missing}. 이대로 두면 이 이름으로 스캔된 의류가 기본계수로 계산되고 "
        "잘못된 건강도가 옷장에 저장됩니다."
    )


def test_frontend_alias_map_points_at_the_same_standard_name():
    frontend_map = load_frontend_alias_map()

    mismatched = sorted(
        (alias, frontend_map[alias], name_en)
        for alias, name_en in iter_seed_aliases()
        if alias in frontend_map and frontend_map[alias] != name_en
    )

    assert not mismatched, (
        "프론트가 서버와 다른 표준명으로 해석하는 별칭입니다 "
        f"(별칭, 프론트, 서버): {mismatched}"
    )


def test_frontend_alias_map_has_no_unknown_entries():
    """서버에 없는 이름을 프론트가 임의로 인정하지 않는지 확인한다.

    서버가 모르는 이름은 저장 단계(`/api/carbon/calculate`)에서
    400 MATERIAL_NOT_FOUND로 거부된다. 프론트만 알아보면 프리뷰에는
    그럴듯한 값이 뜨는데 저장은 실패하는 어긋남이 생긴다.
    """

    frontend_map = load_frontend_alias_map()
    server_aliases = {alias for alias, _ in iter_seed_aliases()}

    unknown = sorted(set(frontend_map) - server_aliases)

    assert not unknown, (
        "서버 소재 표에 없는 별칭이 프론트 표에 있습니다: "
        f"{unknown}. 서버가 모르는 이름은 저장 단계에서 400으로 거부됩니다."
    )


# --- 계수 숫자 --------------------------------------------------------------


def test_frontend_factor_map_covers_every_seed_material():
    frontend_factors = load_frontend_factor_map()
    assert frontend_factors, "프론트 계수표가 비어 있습니다."

    missing = sorted(set(seed_factors()) - set(frontend_factors))

    assert not missing, (
        f"프론트 계수표에 없는 서버 소재입니다: {missing}. "
        "빠진 소재는 기본계수로 떨어져 프리뷰와 저장값이 어긋납니다."
    )


def test_frontend_factor_values_match_the_seed():
    frontend_factors = load_frontend_factor_map()
    server = seed_factors()

    mismatched = sorted(
        (name, frontend_factors[name], factor)
        for name, factor in server.items()
        if name in frontend_factors and frontend_factors[name] != factor
    )

    assert not mismatched, (
        "프론트 계수가 서버 시드와 다릅니다 (소재, 프론트, 서버): "
        f"{mismatched}. 저장 전 프리뷰와 저장 후 표시가 그만큼 벌어집니다."
    )


def test_frontend_factor_map_has_no_unknown_materials():
    """서버에 없는 소재를 프론트가 임의로 계산하지 않는지 확인한다."""

    frontend_factors = load_frontend_factor_map()

    unknown = sorted(set(frontend_factors) - set(seed_factors()))

    assert not unknown, (
        f"서버 소재 표에 없는 소재가 프론트 계수표에 있습니다: {unknown}. "
        "프리뷰에는 값이 뜨는데 저장은 400으로 거부됩니다."
    )


# --- 파서 자체 --------------------------------------------------------------


_SAMPLE = """
  /// _emissionFactorsByStandardName = { 문서 주석 안의 가짜 마커 }
  static const Map<String, String> _standardNamesByAlias = {
    '면': 'cotton',
    // '캐시미어': 'cashmere',
    '울': 'wool',   // 서버 별칭
  };

  static const Map<String, double> _emissionFactorsByStandardName = {
    'cotton': 8.3,
    // 'cashmere': 30.0,
  };
"""


def test_parser_ignores_commented_out_entries():
    """주석 처리된 항목을 살아 있는 것으로 읽으면 죽은 매핑이 초록으로 나간다."""

    aliases = dict(parse_dart_map(_SAMPLE, "_standardNamesByAlias = {", _ALIAS_ENTRY))

    assert aliases == {"면": "cotton", "울": "wool"}, (
        "주석 처리된 별칭이 살아 있는 항목으로 읽혔습니다."
    )


def test_parser_ignores_commented_out_factors():
    factors = dict(
        parse_dart_map(_SAMPLE, "_emissionFactorsByStandardName = {", _FACTOR_ENTRY)
    )

    assert factors == {"cotton": "8.3"}, "주석 처리된 계수가 살아 있는 항목으로 읽혔습니다."


def test_parser_does_not_start_at_a_marker_inside_a_doc_comment():
    """문서 주석이 표 이름을 그대로 담고 있어도 진짜 표에서 시작해야 한다."""

    factors = dict(
        parse_dart_map(_SAMPLE, "_emissionFactorsByStandardName = {", _FACTOR_ENTRY)
    )

    assert factors, "문서 주석의 가짜 마커에서 파싱을 시작해 표를 놓쳤습니다."


def test_parser_keeps_slashes_inside_string_literals():
    source = "_standardNamesByAlias = {\n    'a//b': 'cotton',\n  };"
    aliases = dict(parse_dart_map(source, "_standardNamesByAlias = {", _ALIAS_ENTRY))

    assert aliases == {"a//b": "cotton"}
