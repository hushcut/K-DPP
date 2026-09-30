"""Safe CLI for validating, publishing and retiring versioned carbon policies."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from sqlalchemy.orm import Session

import database


class FactorManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material: str = Field(min_length=1)
    factor_key: str = Field(min_length=1)
    version: str = Field(min_length=1)
    value_decimal: str = Field(pattern=r"^(0|[1-9]\d*)(\.\d+)?$")
    unit: Literal["kg CO2eq/kg fiber"]
    method: str = Field(min_length=1)
    scope: Literal["fiber_production_estimate"]
    product_form: str = Field(min_length=1)
    production_system: str = Field(min_length=1)
    geography: str = Field(default="unknown", min_length=1)
    publication_year: int | None = Field(default=None, ge=1900, le=2100)
    data_years: list[int] = Field(default_factory=list)
    source_name: str = Field(min_length=1)
    source_url: HttpUrl
    source_locator: str = Field(min_length=1)
    evidence_type: Literal["literature", "derived"]
    usage_scope: Literal["public_estimate", "research_scenario"]
    limitations: list[str] = Field(default_factory=list)
    carbon_accounting: dict = Field(default_factory=dict)
    components: dict | None = None
    review_note: str = Field(min_length=1)
    selection_assumption: str = Field(min_length=1)

    @field_validator("data_years")
    @classmethod
    def validate_data_years(cls, value):
        if any(year < 1900 or year > 2100 for year in value):
            raise ValueError("data_years must contain four-digit years")
        return value


class ProfileManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    version: str = Field(min_length=1)
    formula_version: Literal["fiber_mass_v2"]
    method: str = Field(min_length=1)
    scope: Literal["fiber_production_estimate"]
    usage_scope: Literal["public_estimate", "research_scenario"]


class PolicyManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: ProfileManifest
    factors: list[FactorManifest] = Field(min_length=1)

    @field_validator("factors")
    @classmethod
    def unique_materials(cls, value):
        names = [factor.material.strip().lower() for factor in value]
        if len(names) != len(set(names)):
            raise ValueError("each material may appear only once")
        keys = [(factor.factor_key, factor.version) for factor in value]
        if len(keys) != len(set(keys)):
            raise ValueError("factor key/version pairs must be unique")
        return value


def load_manifest(path: Path) -> PolicyManifest:
    return PolicyManifest.model_validate_json(path.read_text(encoding="utf-8"))


def validate_manifest(session: Session, manifest: PolicyManifest) -> dict:
    profile = manifest.profile
    if session.query(database.CalculationProfile).filter_by(
            key=profile.key, version=profile.version).first():
        raise ValueError("profile key/version already exists")
    if session.query(database.CalculationProfile).filter_by(
            status="active", usage_scope=profile.usage_scope).first():
        raise ValueError("an active profile already exists for this usage_scope")

    resolved = []
    for factor in manifest.factors:
        material_name = factor.material.strip().lower()
        material = session.query(database.Material).filter_by(name_en=material_name).first()
        if material is None:
            raise ValueError(f"unknown material: {factor.material}")
        if session.query(database.MaterialFactor).filter_by(
                factor_key=factor.factor_key, version=factor.version).first():
            raise ValueError(f"factor key/version already exists: {factor.factor_key}/{factor.version}")
        if (factor.method != profile.method or factor.scope != profile.scope
                or factor.usage_scope != profile.usage_scope):
            raise ValueError(f"factor is incompatible with profile: {factor.material}")
        resolved.append((factor, material))
    return {
        "profile": f"{profile.key}/{profile.version}",
        "usage_scope": profile.usage_scope,
        "materials": [material.name_en for _, material in resolved],
        "resolved": resolved,
    }


def publish_manifest(session: Session, manifest: PolicyManifest, *, apply: bool) -> dict:
    checked = validate_manifest(session, manifest)
    summary = {key: value for key, value in checked.items() if key != "resolved"}
    summary["status"] = "validated"
    if not apply:
        return summary

    profile_data = manifest.profile
    profile = database.CalculationProfile(key=profile_data.key, version=profile_data.version,
        status="draft", formula_version=profile_data.formula_version, method=profile_data.method,
        scope=profile_data.scope, usage_scope=profile_data.usage_scope)
    session.add(profile)
    session.flush()
    for factor_data, material in checked["resolved"]:
        factor = database.MaterialFactor(factor_key=factor_data.factor_key,
            version=factor_data.version, material_id=material.id,
            value_decimal=factor_data.value_decimal, unit=factor_data.unit,
            method=factor_data.method, scope=factor_data.scope,
            product_form=factor_data.product_form,
            production_system=factor_data.production_system,
            geography=factor_data.geography, publication_year=factor_data.publication_year,
            data_years_json=json.dumps(factor_data.data_years),
            source_name=factor_data.source_name, source_url=str(factor_data.source_url),
            source_locator=factor_data.source_locator,
            evidence_type=factor_data.evidence_type, review_status="selected",
            usage_scope=factor_data.usage_scope,
            limitations_json=json.dumps(factor_data.limitations, ensure_ascii=False),
            carbon_accounting_json=json.dumps(factor_data.carbon_accounting, ensure_ascii=False),
            components_json=(json.dumps(factor_data.components, ensure_ascii=False)
                             if factor_data.components is not None else None),
            reviewed_at=database.utc_now(), review_note=factor_data.review_note)
        session.add(factor)
        session.flush()
        session.add(database.ProfileFactor(profile_id=profile.id, material_id=material.id,
            factor_id=factor.id, selection_assumption=factor_data.selection_assumption))
    session.flush()
    profile.status = "active"
    session.commit()
    summary.update(status="published", profile_id=profile.id)
    return summary


def retire_profile(session: Session, key: str, version: str, *, apply: bool) -> dict:
    profile = session.query(database.CalculationProfile).filter_by(key=key, version=version).first()
    if profile is None:
        raise ValueError("profile not found")
    if profile.status != "active":
        raise ValueError("only an active profile can be retired")
    result = {"profile": f"{key}/{version}", "status": "validated"}
    if apply:
        profile.status = "retired"
        session.commit()
        result["status"] = "retired"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage versioned K-DPP carbon policies safely.")
    commands = parser.add_subparsers(dest="command", required=True)
    publish = commands.add_parser("publish", help="Validate a manifest; write only with --apply.")
    publish.add_argument("manifest", type=Path)
    publish.add_argument("--apply", action="store_true")
    retire = commands.add_parser("retire", help="Validate retirement; write only with --apply.")
    retire.add_argument("key")
    retire.add_argument("version")
    retire.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    try:
        with database.SessionLocal() as session:
            if args.command == "publish":
                result = publish_manifest(session, load_manifest(args.manifest), apply=args.apply)
            else:
                result = retire_profile(session, args.key, args.version, apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
