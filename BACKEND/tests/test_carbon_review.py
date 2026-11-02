"""Regression coverage for PR 88 review feedback."""
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import database
from carbon.api import CalculationRequest
from carbon.policy_admin import PolicyManifest, main, publish_manifest
from carbon.public_policy import approved_public_manifest
from test_policy_admin import manifest
from test_carbon_v2 import URL, PAYLOAD, login, seed_profile


def test_large_material_map_rejected_before_item_validation():
    with pytest.raises(ValidationError) as error:
        CalculationRequest.model_validate({**PAYLOAD,
            "materials": {str(i): "not-a-number" for i in range(70000)}})
    assert len(error.value.errors()) == 1
    assert error.value.errors()[0]["type"] == "too_long"


@pytest.mark.parametrize("extra", [
    {"materials": {"x" * 65: 100}}, {"raw_ocr_text": "x" * 4001},
    {"materials": {"cotton": True}},
])
def test_request_resource_limits(extra):
    with pytest.raises(ValidationError):
        CalculationRequest.model_validate({**PAYLOAD, **extra})


@pytest.mark.parametrize("value", ["0", "1000000000001", "0.0000000000001", "9" * 100])
def test_invalid_factor_values_rejected(value):
    with pytest.raises(ValueError):
        manifest(value_decimal=value)


def test_public_policy_cannot_promote_arbitrary_evidence(client):
    data = manifest().model_dump(mode="json")
    data["profile"]["usage_scope"] = "public_estimate"
    data["factors"][0]["usage_scope"] = "public_estimate"
    with database.SessionLocal() as session:
        with pytest.raises(ValueError, match="reviewed IDEMAT"):
            publish_manifest(session, PolicyManifest.model_validate(data), apply=False,
                             free_public_release=True)
        with pytest.raises(ValueError, match="acknowledgement"):
            publish_manifest(session, approved_public_manifest(), apply=False)


def test_public_policy_and_lightweight_owned_history(client):
    with database.SessionLocal() as session:
        publish_manifest(session, approved_public_manifest(), apply=True, free_public_release=True)
        factor = session.query(database.MaterialFactor).first()
        assert factor.reviewed_at.year == 2026
        assert json.loads(factor.review_note)["approval_reviewer"] is None
    headers = login(client)
    result = client.post(URL, json={**PAYLOAD, "weight_grams": 500,
        "materials": {"cotton": 60, "polyester": 40}}, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["carbon_footprint"] == 0.85
    history = client.get("/me/history", headers=headers)
    assert len(history.content) < 4000
    item = history.json()["history"][0]
    assert item["calculation_snapshot"] is None
    assert client.get(item["provenance_url"], headers=headers).json()["calculation_snapshot"]
    other = login(client, "other-v2@example.com")
    assert client.get(item["provenance_url"], headers=other).status_code == 404


def test_unknown_material_contract(client):
    headers = login(client)
    seed_profile()
    response = client.post(URL, json={**PAYLOAD, "materials": {"unknown-fiber": 100}}, headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"]["unknown_materials"] == ["unknown-fiber"]


def test_atomic_replacement_and_failed_replacement_preserve_old(client):
    with database.SessionLocal() as session:
        publish_manifest(session, manifest(), apply=True)
        data = manifest().model_dump(mode="json")
        data["profile"]["version"] = "2"
        data["factors"][0]["version"] = "2"
        replacement = PolicyManifest.model_validate(data)
        publish_manifest(session, replacement, apply=False, replace_active=True)
        assert session.query(database.CalculationProfile).filter_by(status="active").one().version == "1"
        publish_manifest(session, replacement, apply=True, replace_active=True)
        assert session.query(database.CalculationProfile).filter_by(status="active").one().version == "2"
        assert session.query(database.CalculationProfile).filter_by(status="retired").count() == 1


def test_cli_exit_codes_and_dry_run(client, tmp_path, capsys):
    path = tmp_path / "policy.json"
    path.write_text(manifest().model_dump_json(), encoding="utf-8")
    assert main(["publish", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "validated"
    assert main(["publish", str(path), "--apply"]) == 0
    capsys.readouterr()
    assert main(["publish", str(path), "--apply"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"
    with pytest.raises(SystemExit) as error:
        main(["publish"])
    assert error.value.code == 2


def test_frozen_migration_guard_ddl():
    path = Path(database.BACKEND_DIR) / "migrations/carbon_v2_guards.py"
    # Normalize checkout line endings; a deliberate DDL change needs a new migration.
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert hashlib.sha256(content.encode()).hexdigest() == "fc042fb76cb32234dbb904079f0e2f94c30b8ec220627cc5e2088187b4874198"


def test_real_concurrent_idempotent_requests(client):
    from test_withdraw_calculate_race import _run_while_paused
    headers = {**login(client), "Idempotency-Key": "concurrent-review"}
    seed_profile()
    def calculate():
        return client.post(URL, json=PAYLOAD, headers=headers)
    first, second = _run_while_paused("INSERT INTO analysis_results", calculate, calculate)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    with database.SessionLocal() as session:
        assert session.query(database.AnalysisResult).count() == 1


def test_replacement_rolls_back_if_commit_fails(client, monkeypatch):
    with database.SessionLocal() as session:
        publish_manifest(session, manifest(), apply=True)
        data = manifest().model_dump(mode="json")
        data["profile"]["version"] = data["factors"][0]["version"] = "2"
        def fail_commit():
            raise RuntimeError("simulated commit failure")
        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="simulated"):
            publish_manifest(session, PolicyManifest.model_validate(data), apply=True, replace_active=True)
    with database.SessionLocal() as session:
        assert session.query(database.CalculationProfile).filter_by(status="active").one().version == "1"
        assert session.query(database.CalculationProfile).count() == 1
        assert session.query(database.MaterialFactor).count() == 1


def test_history_200_results_stays_compact(client):
    headers = login(client)
    seed_profile()
    assert client.post(URL, json=PAYLOAD, headers=headers).status_code == 200
    with database.SessionLocal() as session:
        first = session.query(database.AnalysisResult).one()
        for _ in range(199):
            session.add(database.AnalysisResult(user_id=first.user_id, materials=first.materials,
                carbon_footprint=first.carbon_footprint, unit=first.unit,
                result_kind=first.result_kind, formula_version=first.formula_version,
                profile_id=first.profile_id, snapshot_schema_version=first.snapshot_schema_version,
                calculation_snapshot_json=first.calculation_snapshot_json))
        session.commit()
    response = client.get("/me/history", headers=headers)
    assert len(response.json()["history"]) == 200
    assert len(response.content) < 512000
