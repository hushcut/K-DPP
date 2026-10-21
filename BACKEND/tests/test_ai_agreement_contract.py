"""AI 담당 연동 협의안(10-15)의 서버 몫을 붙들어 둔다(DECISIONS 255).

- R1: 계산 API 가 입력을 거절(400·422)하면 서버 이력에 아무것도 남지 않는다.
- R2: 스캔의 `is_supported` 와 계산 API 의 `unknown_materials` 는 같은 소재 표로 판정한다.
  AI 가 알아보는 소재 중 서버 표에 없는 것(10-17 기준 acetate·alpaca·hemp·triacetate)은
  스캔에서 이름을 그대로 둔 채 미지원으로 보이고, 계산은 400 으로 거절된다.
- R4: AI 의 `warnings` 는 200 과 422 모두 그대로 전달된다. 서버가 모르는 코드도 걸러지지 않는다.

앱은 이 세 가지를 믿고 '계산 거절이면 저장하지 않음'·'미지원 소재는 계산 불가 안내'를 붙인다.
"""

import database
import init_data
import main
from apps.text import rules
from auth_helpers import signup


# 응답 공개 범위는 warnings 뿐이다(DECISIONS 210).
INTERNAL_KEYS = ("ocr", "confidence", "parse_evidence", "selected_part")


def login(client, email):
    signup(client, email, nickname="agreement")
    token = client.post(
        "/auth/login", json={"email": email, "password": "password123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def scan_with_parsed(client, headers, monkeypatch, parsed):
    # raw_ocr_text 길은 Vision 을 부르지 않는다. 파서 결과만 바꿔 끼워 서버의 판정·전달을 본다.
    monkeypatch.setattr(main, "parse_label", lambda text: {"raw_ocr_preview": text, **parsed})
    return client.post(
        "/api/scan",
        files={"image": ("label.jpg", b"\xff\xd8\xff\xe0", "image/jpeg")},
        data={"raw_ocr_text": "label"},
        headers=headers,
    )


def saved_rows() -> int:
    with database.SessionLocal() as session:
        return session.query(database.AnalysisResult).count()


def test_rejected_calculations_leave_no_history(client):
    headers = login(client, "reject@example.com")
    rejected = [
        ({"materials": {"acetate": 60, "cotton": 40}, "weight_grams": 300}, 400, "MATERIAL_NOT_FOUND"),
        ({"materials": {"cotton": 80, "polyester": 10}, "weight_grams": 300}, 400, "MATERIAL_RATIO_INVALID"),
        ({"materials": {"cotton": -5, "polyester": 105}, "weight_grams": 300}, 400, "MATERIAL_RATIO_INVALID"),
        ({"materials": {}, "weight_grams": 300}, 400, "MATERIAL_MISSING"),
        ({"materials": {"cotton": 100}, "weight_grams": 0}, 400, "WEIGHT_INVALID"),
        ({"materials": {"cotton": 100}}, 400, "WEIGHT_MISSING"),
        ({"materials": {"cotton": 100}, "min_weight_grams": 300, "max_weight_grams": 100}, 400, "WEIGHT_RANGE_INVALID"),
        (
            {"materials": {f"m{i}": 1 for i in range(main.MAX_MATERIAL_ENTRIES + 1)}, "weight_grams": 300},
            422,
            "VALIDATION_ERROR",
        ),
        ({"materials": {"cotton": "많이"}, "weight_grams": 300}, 422, "VALIDATION_ERROR"),
    ]

    for payload, status, error_code in rejected:
        response = client.post("/api/carbon/calculate", json=payload, headers=headers)
        assert response.status_code == status, payload
        assert response.json()["error_code"] == error_code, payload
        assert "saved_result_id" not in response.json(), payload

    assert client.get("/me/history", headers=headers).json()["history"] == []
    assert saved_rows() == 0

    # 위의 0 이 '아예 저장이 안 되는 환경'이 아님을 보인다.
    accepted = client.post(
        "/api/carbon/calculate", json={"materials": {"cotton": 100}, "weight_grams": 300}, headers=headers
    )
    assert accepted.status_code == 200
    assert len(client.get("/me/history", headers=headers).json()["history"]) == 1


def test_scan_support_flag_matches_calculation_for_every_ai_material(client, monkeypatch):
    headers = login(client, "support@example.com")
    seed_names = {seed["name_en"] for seed in init_data.MATERIAL_SEEDS}
    unsupported = []

    for name in rules.MATERIAL_ALIASES:
        scan = scan_with_parsed(client, headers, monkeypatch, {"status": "success", "materials": {name: 100}})
        assert scan.status_code == 200, name
        # 스캔은 인식한 소재명을 바꾸지 않는다.
        assert scan.json()["materials"] == {name: 100}
        [detail] = scan.json()["material_details"]

        calculation = client.post(
            "/api/carbon/calculate", json={"materials": {name: 100}, "weight_grams": 300}, headers=headers
        )
        if detail["is_supported"]:
            assert calculation.status_code == 200, name
        else:
            assert calculation.status_code == 400, name
            assert calculation.json()["error_code"] == "MATERIAL_NOT_FOUND"
            assert calculation.json()["detail"]["unknown_materials"] == [name]
            unsupported.append(name)

    # 미지원 = AI 사전에는 있고 서버 소재 표에는 없는 이름. 소재를 더하면(R3 승인 출처 뒤) 저절로 줄어든다.
    assert sorted(unsupported) == sorted(set(rules.MATERIAL_ALIASES) - seed_names)
    assert unsupported, "AI 사전과 서버 표가 같아졌다면 이 시험의 미지원 쪽은 더 이상 아무것도 보지 않는다"


def test_ai_warnings_pass_through_on_200_and_422(client, monkeypatch):
    headers = login(client, "warnings@example.com")
    # 하나는 지금 AI 가 내는 코드, 하나는 협의 중인 예시(서버가 모르는 코드)다.
    codes = ["manual_composition_review_required:outer", "composition_part:unidentified"]
    internal = {key: {"x": 1} for key in INTERNAL_KEYS}

    success = scan_with_parsed(
        client,
        headers,
        monkeypatch,
        {"status": "success", "materials": {"cotton": 100}, "warnings": [*codes, 123, None], **internal},
    )
    assert success.status_code == 200
    assert success.json()["warnings"] == codes
    assert not any(key in success.json() for key in INTERNAL_KEYS)

    failure = scan_with_parsed(
        client,
        headers,
        monkeypatch,
        {
            "status": "failed",
            "error_code": "manual_composition_review_required",
            "materials": {"cotton": 95},
            "warnings": codes,
            **internal,
        },
    )
    detail = failure.json()["detail"]
    assert failure.status_code == 422
    assert detail["warnings"] == codes
    assert detail["materials"] == {}
    assert detail["partial_materials"] == {"cotton": 95}
    assert not any(key in detail for key in INTERNAL_KEYS)
    # 스캔은 어느 쪽이든 저장하지 않는다.
    assert saved_rows() == 0
