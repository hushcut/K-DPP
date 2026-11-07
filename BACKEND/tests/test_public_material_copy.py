"""앱이 가진 서버 공개(V2) 계수 소재 목록 사본이 선정 JSON 과 같은지 본다(#113 리뷰 3번).

앱은 로그인 계정의 옷을 서버가 답하지 못할 때(끊김·세션 만료) 이 목록으로 저장을 막고, 미리보기도
이 목록으로 '계산 기준이 없는 소재'를 알린다. 어긋나면 서버가 받는 소재를 막거나, 서버가 거절할
소재를 옛 소재표 값으로 저장한다.
"""
import re

from carbon.public_policy import load_selection
from test_material_name_contract import FACTOR_PATH, _read_dart_map


def test_app_public_material_copy_matches_selection():
    entries = _read_dart_map(FACTOR_PATH, "_publicFactorMaterials = {", re.compile(r"'([^']+)'\s*,"))
    assert sorted(entries) == sorted(item["material"] for item in load_selection()["factors"])
