"""2026-11-07 공개 계수(IDEMAT 2026 RevB2) 추가분 — 원본에서 다시 읽은 값과 결과 안내문."""
from decimal import ROUND_HALF_UP, Decimal

import pytest

import database
from carbon.policy_admin import publish_manifest
from carbon.public_policy import approved_public_manifest, load_selection
from test_carbon_v2 import URL, PAYLOAD, login

# Idemat_2026RevB2.xlsx(sha256 31253400…) Idemat2026 시트 G열을 2026-11-07 에 다시 읽은 값.
SOURCE_G = {
    1106: "5.13", 1111: "0.9358808000000001", 1112: "3.705373066666667", 1119: "5.46",
    1120: "2.0377328", 1123: "1.5", 1124: "61.09769333333334", 1126: "1.5057799333333333",
    1143: "0.794138", 1165: "0.4291713933333334", 6: "16.419932",
}
EXPECTED = {
    "cotton": "0.9358808000000001", "polyester": "2.8318708", "acrylic": "5.13",
    "linen": "1.5057799333333333", "nylon": "6.254138", "spandex": "4.499511066666667",
    "polyurethane": "4.499511066666667", "rayon": "1.5", "viscose": "1.5", "modal": "1.5",
    "wool": "61.09769333333334", "leather": "16.419932", "down": "0.4291713933333334",
    "feather": "0.4291713933333334",
}


def factors():
    return {item["material"]: item for item in load_selection()["factors"]}


def test_selection_values_match_source_rows():
    selected = factors()
    assert {name: item["value_decimal"] for name, item in selected.items()} == EXPECTED
    for item in selected.values():
        rows = {int(cell.split("!")[1][1:]) for cell in item["source_cells"]}
        values = [Decimal(SOURCE_G[row]) for row in sorted(rows)]
        assert sum(values) == Decimal(item["value_decimal"]), item["material"]
        two = Decimal(item["value_decimal"]).quantize(Decimal("0.01"), ROUND_HALF_UP)
        assert item["display_value"] == str(two), item["material"]


def test_derived_expressions_add_up():
    for item in factors().values():
        derivation = item.get("derivation")
        if item["evidence_type"] != "derived":
            assert derivation is None
            continue
        parts = [Decimal(v) for k, v in derivation.items() if k.endswith("_kgCO2eq_per_kg")]
        assert len(parts) == 2
        assert sum(parts) == Decimal(item["value_decimal"])
        assert derivation["expression"].endswith("= " + item["value_decimal"])


def test_viscose_family_does_not_add_spinning_and_feather_uses_down_row():
    selected = factors()
    for name in ("rayon", "viscose", "modal"):
        assert selected[name]["source_cells"] == ["Idemat2026!A1123", "Idemat2026!F1123", "Idemat2026!G1123"]
        assert "Idemat2026!G1144" not in selected[name]["source_cells"]
    assert selected["feather"]["source_cells"] == selected["down"]["source_cells"]


def test_every_selected_factor_has_provenance_and_korean_note_where_assumed():
    for item in factors().values():
        assert item["reviewed_on"] in ("2026-10-18", "2026-11-07")
        assert item["technical_selector"].endswith("(user-delegated)")
        if item["reviewed_on"] == "2026-11-07":
            assert item["display_note_ko"].endswith("니다.")


def selected_factor(session, name):
    # 비밀정보 검사(gitleaks generic-api-key)가 '이름=따옴표 값' 꼴을 키로 보므로 소재 id 로 찾는다.
    material = session.query(database.Material).filter_by(name_en=name).one()
    return session.query(database.MaterialFactor).filter_by(material_id=material.id).one()


def test_manifest_publishes_all_materials(client):
    with database.SessionLocal() as session:
        result = publish_manifest(session, approved_public_manifest(), apply=True,
                                  free_public_release=True)
        assert sorted(result["materials"]) == sorted(EXPECTED)
        nylon = selected_factor(session, "nylon")
        assert nylon.version == "2026-11-07-v1"
        assert nylon.reviewed_at.date().isoformat() == "2026-11-07"
        cotton = selected_factor(session, "cotton")
        assert cotton.reviewed_at.date().isoformat() == "2026-10-18"


@pytest.mark.parametrize("materials, weight, footprint, notes, absent", [
    ({"nylon": 95, "spandex": 5}, 200, 1.23, ["나일론은", "스판덱스·폴리우레탄은"], ["폴리에스터는"]),
    ({"폴리에스터": 90, "폴리우레탄": 10}, 200, 0.6, ["폴리에스터는", "스판덱스·폴리우레탄은"], []),
    ({"rayon": 50, "viscose": 30, "modal": 20}, 200, 0.3, ["레이온·비스코스·모달은"], []),
    ({"wool": 100}, 300, 18.33, ["울은 호주산"], []),
    ({"leather": 100}, 500, 8.21, ["가죽은 크롬 무두질"], []),
    ({"오리솜털": 80, "오리깃털": 20}, 300, 0.13, ["다운·깃털은"], []),
    ({"cotton": 100}, 200, 0.19, [], ["대체값", "사례"]),
])
def test_new_public_materials_calculate_with_one_note_each(client, materials, weight, footprint,
                                                           notes, absent):
    with database.SessionLocal() as session:
        publish_manifest(session, approved_public_manifest(), apply=True, free_public_release=True)
    headers = login(client)
    response = client.post(URL, json={**PAYLOAD, "materials": materials, "weight_grams": weight},
                           headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["carbon_footprint"] == footprint
    assert body["profile_version"] == "2026-11-07-v1"
    note = body["calculation_note"]
    for text in notes:
        assert note.count(text) == 1, note
    for text in absent:
        assert text not in note, note


@pytest.mark.parametrize("material", ["cashmere", "silk", "lyocell", "cupro", "bamboo", "yak"])
def test_unselected_materials_still_rejected(client, material):
    with database.SessionLocal() as session:
        publish_manifest(session, approved_public_manifest(), apply=True, free_public_release=True)
    headers = login(client)
    response = client.post(URL, json={**PAYLOAD, "materials": {"cotton": 50, material: 50}},
                           headers=headers)
    assert response.status_code == 422
    assert response.json()["detail"]["unknown_materials"] == [material]
