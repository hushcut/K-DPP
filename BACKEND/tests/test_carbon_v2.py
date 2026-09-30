"""Synthetic factors only: these fixtures do not approve real literature values."""
import json
import pytest
from sqlalchemy.exc import IntegrityError
import database

URL = "/api/v2/carbon/calculate"
PAYLOAD = {"materials": {"cotton": 100}, "weight_grams": 200, "composition_scope": "single"}


def login(client, email="v2@example.com"):
    client.post("/auth/signup", json={"email": email, "nickname": "tester", "password": "password123"})
    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def seed_profile():
    with database.SessionLocal() as db:
        cotton = db.query(database.Material).filter_by(name_en="cotton").one()
        profile = database.CalculationProfile(key="fixture", version="1", status="draft",
            formula_version="fiber_mass_v2", method="test-method", scope="fiber_production_estimate",
            usage_scope="public_estimate")
        factor = database.MaterialFactor(factor_key="fixture", version="1", material_id=cotton.id,
            value_decimal="8.3", unit="kg CO2eq/kg fiber", method="test-method",
            scope="fiber_production_estimate", product_form="fixture", production_system="fixture",
            source_name="TEST ONLY", source_url="https://example.invalid", source_locator="fixture",
            evidence_type="derived", review_status="selected", usage_scope="public_estimate")
        db.add_all([profile, factor])
        db.flush()
        db.add(database.ProfileFactor(profile_id=profile.id, material_id=cotton.id,
                                      factor_id=factor.id, selection_assumption="synthetic test"))
        db.commit()
        profile.status = "active"
        db.commit()


def test_v2_snapshot_and_replay_survive_profile_retirement(client):
    headers = login(client)
    seed_profile()
    headers["Idempotency-Key"] = "replay"
    first = client.post(URL, json=PAYLOAD, headers=headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["carbon_footprint"] == 1.66
    with database.SessionLocal() as db:
        db.query(database.CalculationProfile).one().status = "retired"
        db.commit()
    retry = client.post(URL, json={**PAYLOAD, "weight_grams": "200.0"}, headers=headers)
    assert retry.json() == body
    history = client.get("/me/history", headers=headers).json()["history"]
    assert len(history) == 1
    snapshot = history[0]["calculation_snapshot"]
    assert snapshot["factors"][0]["value_decimal"] == "8.3"
    assert snapshot["results"]["raw"]["representative"] == "1.66"
    assert history[0]["provenance_status"] == "available"
    assert client.post(URL, json={**PAYLOAD, "weight_grams": 300}, headers=headers).status_code == 409


def test_v2_catalog_and_direct_priority(client):
    headers = login(client)
    seed_profile()
    payload = {"materials": {"면": 50, "cotton": 50}, "composition_scope": "single",
               "clothing_type_id": "short_sleeve_tshirt"}
    result = client.post(URL, json=payload, headers=headers).json()
    assert result["carbon_footprint"] == 1.49
    assert result["weight_source"] == "catalog"
    assert result["weight_evidence_type"] == "placeholder"
    result = client.post(URL, json={**payload, "weight_grams": 300}, headers=headers).json()
    assert result["carbon_footprint"] == 2.49
    assert result["weight_source"] == "direct"


@pytest.mark.parametrize("extra,code", [
    ({"composition_scope": "multiple"}, "COMPOSITION_SCOPE_UNSUPPORTED"),
    ({"clothing_type_id": "invalid"}, "CLOTHING_TYPE_INVALID"),
    ({"weight_grams": 0}, "WEIGHT_INVALID"),
    ({"materials": {"not-found": 100}}, "MATERIAL_NOT_FOUND"),
    ({"materials": {"cotton": 90}}, "MATERIAL_RATIO_INVALID"),
    ({"materials": {"polyester": 100}}, "FACTOR_UNAVAILABLE"),
])
def test_v2_failures_never_save(client, extra, code):
    headers = login(client)
    seed_profile()
    response = client.post(URL, json={**PAYLOAD, **extra}, headers=headers)
    assert response.json()["error_code"] == code, response.text
    with database.SessionLocal() as db:
        assert db.query(database.AnalysisResult).count() == 0


def test_v2_requires_auth_and_selected_profile(client):
    assert client.post(URL, json=PAYLOAD).status_code == 401
    headers = login(client)
    assert client.post(URL, json=PAYLOAD, headers=headers).status_code == 503
    seed_profile()
    with database.SessionLocal() as db:
        # Simulate a legacy/corrupt selection created before immutability guards.
        db.connection().exec_driver_sql("DROP TRIGGER trg_selected_factor_no_update")
        db.query(database.MaterialFactor).one().review_status = "candidate"
        db.commit()
    response = client.post(URL, json=PAYLOAD, headers=headers)
    assert response.status_code == 422
    assert response.json()["error_code"] == "FACTOR_UNAVAILABLE"


def test_v2_account_scoped_keys(client):
    first = login(client, "first@example.com")
    second = login(client, "second@example.com")
    seed_profile()
    for headers in (first, second):
        headers["Idempotency-Key"] = "same-key"
        assert client.post(URL, json=PAYLOAD, headers=headers).status_code == 200
    a = client.get("/me/history", headers=first).json()["history"]
    b = client.get("/me/history", headers=second).json()["history"]
    assert len(a) == len(b) == 1
    assert a[0]["id"] != b[0]["id"]


@pytest.mark.parametrize("value", [True, "NaN", "Infinity", "1e100", "0e-100000"])
def test_v2_invalid_measurements(client, value):
    response = client.post(URL, json={**PAYLOAD, "weight_grams": value}, headers=login(client))
    assert response.status_code == 422


def test_v1_history_has_no_fabricated_provenance(client):
    headers = login(client)
    response = client.post("/api/carbon/calculate", json=PAYLOAD, headers=headers)
    assert response.status_code == 200
    history = client.get("/me/history", headers=headers).json()["history"][0]
    assert history["provenance_status"] == "unavailable"
    assert history["calculation_snapshot"] is None


def test_nonstandard_nan_json_returns_validation_error(client):
    response = client.post(URL, content='{"materials":{"cotton":100},"weight_grams":NaN,"composition_scope":"single"}',
                           headers={**login(client), "Content-Type": "application/json"})
    assert response.status_code == 422


def test_failed_commit_does_not_leave_result(client, monkeypatch):
    from sqlalchemy.orm import Session
    headers = login(client)
    seed_profile()
    def broken_commit(self):
        self.flush()
        raise RuntimeError("simulated database failure")
    monkeypatch.setattr(Session, "commit", broken_commit)
    with pytest.raises(RuntimeError, match="simulated database failure"):
        client.post(URL, json=PAYLOAD, headers=headers)
    with database.SessionLocal() as db:
        assert db.query(database.AnalysisResult).count() == 0


def test_multiple_active_profiles_fail_closed(client):
    headers = login(client)
    seed_profile()
    with database.SessionLocal() as db:
        # Simulate a legacy/corrupt database created before activation guards existed.
        with pytest.raises(IntegrityError):
            db.execute(database.CalculationProfile.__table__.insert().values(key="other", version="1",
                status="active", formula_version="fiber_mass_v2", method="test-method",
                scope="fiber_production_estimate", usage_scope="public_estimate"))
        db.rollback()
        db.connection().exec_driver_sql("DROP TRIGGER trg_profile_insert_as_draft")
        db.execute(database.CalculationProfile.__table__.insert().values(key="other", version="1",
            status="active", formula_version="fiber_mass_v2", method="test-method",
            scope="fiber_production_estimate", usage_scope="public_estimate"))
        db.commit()
    assert client.post(URL, json=PAYLOAD, headers=headers).status_code == 503


def test_corrupt_snapshot_does_not_break_history(client):
    headers = login(client)
    with database.SessionLocal() as db:
        user = db.query(database.User).filter_by(email="v2@example.com").one()
        db.add(database.AnalysisResult(user_id=user.id, materials='{"cotton": 100}',
            carbon_footprint=1.23, unit="kg CO2eq", result_kind="garment_estimate",
            formula_version="fiber_mass_v2", snapshot_schema_version=1,
            calculation_snapshot_json="{broken"))
        db.commit()
    response = client.get("/me/history", headers=headers)
    assert response.status_code == 200
    result = response.json()["history"][0]
    assert result["provenance_status"] == "invalid"
    assert result["calculation_snapshot"] is None


def test_corrupt_snapshot_cannot_be_replayed(client):
    headers = login(client)
    seed_profile()
    headers["Idempotency-Key"] = "corrupt-replay"
    first = client.post(URL, json=PAYLOAD, headers=headers)
    assert first.status_code == 200
    with database.SessionLocal() as db:
        result = db.query(database.AnalysisResult).one()
        result.calculation_snapshot_json = "{broken"
        db.commit()
    retry = client.post(URL, json=PAYLOAD, headers=headers)
    assert retry.status_code == 500
    assert retry.json()["error_code"] == "SAVED_RESULT_INVALID"
