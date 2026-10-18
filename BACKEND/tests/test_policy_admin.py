"""Policy administration uses synthetic evidence only."""
import pytest

import database
from carbon.policy_admin import PolicyManifest, publish_manifest, retire_profile


def manifest(**factor_overrides):
    factor = {
        "material": "cotton",
        "factor_key": "admin-fixture-cotton",
        "version": "1",
        "value_decimal": "2.88",
        "unit": "kg CO2eq/kg fiber",
        "method": "test-method",
        "scope": "fiber_production_estimate",
        "product_form": "fixture fiber",
        "production_system": "fixture system",
        "geography": "fixture",
        "publication_year": 2026,
        "data_years": [2023],
        "source_name": "TEST ONLY",
        "source_url": "https://example.invalid/report.pdf",
        "source_locator": "fixture table",
        "evidence_type": "literature",
        "usage_scope": "research_scenario",
        "limitations": ["synthetic test value"],
        "carbon_accounting": {"test": True},
        "components": None,
        "review_note": "synthetic fixture",
        "selection_assumption": "test selection only",
    }
    factor.update(factor_overrides)
    return PolicyManifest.model_validate({
        "profile": {
            "key": "admin-fixture",
            "version": "1",
            "formula_version": "fiber_mass_v2",
            "method": "test-method",
            "scope": "fiber_production_estimate",
            "usage_scope": "research_scenario",
        },
        "factors": [factor],
    })


def test_publish_defaults_to_validation_only(client):
    with database.SessionLocal() as session:
        result = publish_manifest(session, manifest(), apply=False)
        assert result["status"] == "validated"
        assert result["materials"] == ["cotton"]
        assert session.query(database.CalculationProfile).count() == 0
        assert session.query(database.MaterialFactor).count() == 0


def test_publish_and_retire_policy(client):
    with database.SessionLocal() as session:
        result = publish_manifest(session, manifest(), apply=True)
        assert result["status"] == "published"
        profile = session.get(database.CalculationProfile, result["profile_id"])
        assert profile.status == "active"
        factor = session.query(database.MaterialFactor).one()
        assert factor.review_status == "selected"
        assert factor.value_decimal == "2.88"
        assert session.query(database.ProfileFactor).one().factor_id == factor.id

        checked = retire_profile(session, "admin-fixture", "1", apply=False)
        assert checked["status"] == "validated"
        assert profile.status == "active"
        retired = retire_profile(session, "admin-fixture", "1", apply=True)
        assert retired["status"] == "retired"
        assert profile.status == "retired"


def test_publish_rejects_incompatible_and_duplicate_manifests(client):
    incompatible = manifest(method="other-method")
    with database.SessionLocal() as session:
        with pytest.raises(ValueError, match="incompatible"):
            publish_manifest(session, incompatible, apply=False)

        publish_manifest(session, manifest(), apply=True)
        with pytest.raises(ValueError, match="already exists"):
            publish_manifest(session, manifest(), apply=False)
