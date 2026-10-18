"""Integration with develop migrations, account lifecycle and the selected research policy."""
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import text

import database
from carbon.policy_admin import load_manifest, publish_manifest
from test_carbon_v2 import login, seed_profile, URL, PAYLOAD

PRE_V2 = "a28c2a50b363"


def test_upgrade_preserves_existing_result_and_materials(alembic_config):
    command.upgrade(alembic_config, PRE_V2)
    with database.engine.begin() as conn:
        before = conn.execute(text("SELECT name_en, carbon_factor FROM materials ORDER BY id")).all()
        conn.execute(text(
            "INSERT INTO analysis_results(materials, carbon_footprint, unit, unknown_materials, created_at) "
            "VALUES ('{}', 12.34, 'kg CO2eq', '[]', CURRENT_TIMESTAMP)"))
    command.upgrade(alembic_config, "head")
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)
    with database.engine.connect() as conn:
        assert conn.execute(text("SELECT name_en, carbon_factor FROM materials ORDER BY id")).all() == before
        assert conn.execute(text(
            "SELECT carbon_footprint, calculation_snapshot_json, profile_id FROM analysis_results"
        )).one() == (12.34, None, None)


def test_selected_research_policy_is_explicit_and_unsupported_fibers_fail(client, monkeypatch):
    manifest = load_manifest(Path(database.BACKEND_DIR) / "policies/textile_exchange_2026_research.json")
    with database.SessionLocal() as session:
        publish_manifest(session, manifest, apply=True)
    headers = login(client)
    # Research evidence must not silently satisfy the default public calculation path.
    assert client.post(URL, json=PAYLOAD, headers=headers).status_code == 503
    monkeypatch.setenv("K_DPP_CARBON_USAGE_SCOPE", "research_scenario")
    response = client.post(URL, json={
        **PAYLOAD, "materials": {"cotton": 60, "polyester": 40}, "weight_grams": 500
    }, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["carbon_footprint"] == 1.77
    assert body["research_only"] is True
    assert body["usage_scope"] == "research_scenario"
    assert "연구용" in body["calculation_note"]
    unsupported = client.post(URL, json={
        **PAYLOAD, "materials": {"cotton": 95, "spandex": 5}
    }, headers=headers)
    assert unsupported.status_code == 422
    assert unsupported.json()["error_code"] == "FACTOR_UNAVAILABLE"
    history = client.get("/me/history", headers=headers).json()["history"]
    assert len(history) == 1
    assert history[0]["calculation_snapshot"]["response"]["research_only"] is True


def test_v2_result_removed_with_account_and_closet(client):
    headers = login(client)
    seed_profile()
    assert client.post(URL, json=PAYLOAD, headers=headers).status_code == 200
    user_id = client.get("/me/history", headers=headers).json()["user"]["id"]
    backup = client.post("/me/closet", json={
        "user_id": user_id, "base_version": 0, "items": []
    }, headers=headers)
    assert backup.status_code == 200, backup.text
    response = client.post("/auth/withdraw", json={"password": "password123"}, headers=headers)
    assert response.status_code == 200, response.text
    with database.SessionLocal() as session:
        assert session.query(database.AnalysisResult).count() == 0
        assert session.query(database.ClosetSnapshot).count() == 0
        assert session.query(database.CalculationProfile).count() == 1


def test_downgrade_refuses_to_erase_v2_evidence(client):
    from conftest import make_alembic_config
    seed_profile()
    with pytest.raises(RuntimeError, match="Carbon V2 data exists"):
        command.downgrade(make_alembic_config(), PRE_V2)
    database.assert_schema_current()


def test_v2_maps_deleted_user_foreign_key_failure_to_401(client, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session
    headers = login(client)
    seed_profile()

    class Diagnostic:
        constraint_name = "fk_analysis_results_user_id_users"

    class DeletedUser(Exception):
        diag = Diagnostic()

    def commit(self):
        raise IntegrityError("INSERT analysis_results", {}, DeletedUser())

    monkeypatch.setattr(Session, "commit", commit)
    response = client.post(URL, json=PAYLOAD, headers=headers)
    assert response.status_code == 401
    with database.SessionLocal() as session:
        assert session.query(database.AnalysisResult).count() == 0


def test_v2_real_withdrawal_and_calculation_races(client):
    from fastapi.testclient import TestClient
    import main
    from test_withdraw_calculate_race import (
        two_devices, withdraw, table_counts, _run_while_paused,
    )
    seed_profile()
    server = TestClient(main.app, raise_server_exceptions=False)
    phone, tablet = two_devices(server, "v2-race@example.com")
    calculate = lambda: server.post(URL, json=PAYLOAD, headers={"Authorization": f"Bearer {tablet}"})
    left, calculated = _run_while_paused(
        "DELETE FROM users", lambda: withdraw(server, phone), calculate)
    assert left.status_code == 200, left.text
    assert calculated.status_code == 401, calculated.text
    assert table_counts() == (0, 0, 0)


def test_v2_result_saved_before_withdrawal_is_deleted(client):
    from fastapi.testclient import TestClient
    import main
    from test_withdraw_calculate_race import (
        two_devices, withdraw, table_counts, _run_while_paused,
    )
    seed_profile()
    server = TestClient(main.app, raise_server_exceptions=False)
    phone, tablet = two_devices(server, "v2-first@example.com")
    calculated, left = _run_while_paused(
        "INSERT INTO analysis_results",
        lambda: server.post(URL, json=PAYLOAD, headers={"Authorization": f"Bearer {tablet}"}),
        lambda: withdraw(server, phone))
    assert calculated.status_code == 200, calculated.text
    assert left.status_code == 200, left.text
    assert table_counts() == (0, 0, 0)
