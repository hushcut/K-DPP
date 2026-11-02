"""V2 API, immutable result snapshots and account-scoped request replay."""
from decimal import Decimal
from typing import Annotated, Literal
import hashlib
import json
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError
import database
from .domain import CarbonError, calculate, normalize
from .factors import resolve_factors
from .input_limits import MaterialName, RawOcrText, reject_too_many_materials


class CalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    materials: Annotated[dict[MaterialName, Decimal], Field(min_length=1, max_length=20),
                         BeforeValidator(reject_too_many_materials)]
    weight_grams: Decimal | None = None
    clothing_type_id: str | None = Field(default=None, max_length=100)
    composition_scope: Literal["single", "unknown", "multiple"]
    raw_ocr_text: RawOcrText | None = None

    @field_validator("materials", "weight_grams", mode="before")
    @classmethod
    def reject_boolean(cls, value):
        reject_too_many_materials(value)
        values = value.values() if isinstance(value, dict) else [value]
        if any(isinstance(item, bool) for item in values):
            raise ValueError("Boolean values are not measurements.")
        return value


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, allow_nan=False)


def fail(code, status=422, **details):
    messages = {
        "CALCULATION_PROFILE_UNAVAILABLE": "사용 가능한 계산 기준이 아직 준비되지 않았습니다.",
        "COMPOSITION_SCOPE_UNSUPPORTED": "전체 소재 비율을 확인할 수 있는 단일 부위만 계산할 수 있습니다.",
        "FACTOR_UNAVAILABLE": "해당 소재에 사용할 계수가 아직 선정되지 않았습니다.",
        "MATERIAL_NOT_FOUND": "등록되지 않은 소재가 있습니다.",
        "WEIGHT_MISSING": "실측 무게 또는 의류 종류를 입력해 주세요.",
        "CLOTHING_TYPE_INVALID": "의류 종류를 확인해 주세요.",
        "IDEMPOTENCY_CONFLICT": "같은 요청 키에 다른 입력값이 사용되었습니다.",
    }
    raise HTTPException(status, detail={"error_code": code,
        "message": messages.get(code, "계산 입력 또는 계수 설정을 확인해 주세요."), **details})


def replay(result, request_hash):
    if result.request_hash != request_hash:
        fail("IDEMPOTENCY_CONFLICT", 409)
    try:
        snapshot = json.loads(result.calculation_snapshot_json)
        response = snapshot["response"]
        if not isinstance(response, dict):
            raise TypeError("snapshot response must be an object")
    except (json.JSONDecodeError, KeyError, TypeError):
        fail("SAVED_RESULT_INVALID", 500)
    return {**response, "saved_result_id": result.id}


def history_provenance(result, *, include_snapshot=False):
    if not result.calculation_snapshot_json:
        return {"provenance_status": "unavailable", "calculation_snapshot": None,
                "result_kind": result.result_kind or "legacy_unknown"}
    try:
        snapshot = json.loads(result.calculation_snapshot_json)
        if not isinstance(snapshot, dict):
            raise TypeError("snapshot must be an object")
    except (json.JSONDecodeError, TypeError):
        return {"provenance_status": "invalid", "calculation_snapshot": None,
                "result_kind": result.result_kind or "legacy_unknown",
                "formula_version": result.formula_version}
    return {"provenance_status": "available", "calculation_snapshot": snapshot if include_snapshot else None,
            "provenance_url": f"/api/v2/carbon/results/{result.id}",
            "result_kind": result.result_kind, "formula_version": result.formula_version}


def build_router(get_db, get_user, clothing_options):
    router = APIRouter()

    @router.get("/api/v2/carbon/results/{result_id}", tags=["v2-carbon"])
    def result_detail(result_id: int, db=Depends(get_db), user=Depends(get_user)):
        result = db.query(database.AnalysisResult).filter_by(id=result_id, user_id=user.id).first()
        if result is None:
            raise HTTPException(404, detail="결과를 찾을 수 없습니다.")
        return history_provenance(result, include_snapshot=True)

    @router.post("/api/v2/carbon/calculate", tags=["v2-carbon"])
    def endpoint(request: CalculationRequest, db=Depends(get_db), user=Depends(get_user),
                 request_key: str | None = Header(default=None, alias="Idempotency-Key",
                                                  min_length=1, max_length=128)):
        payload = request.model_dump(mode="json")
        # Normalize decimal spellings without rounding through Decimal.normalize().
        def canonical_decimal(value):
            text = format(value, "f")
            return text.rstrip("0").rstrip(".") if "." in text else text
        # Domain validation bounds representations before canonical hashing.
        from .domain import number
        try:
            for value in request.materials.values():
                number(value, "MATERIAL_RATIO_INVALID")
            if request.weight_grams is not None:
                number(request.weight_grams, "WEIGHT_INVALID")
                if not Decimal(1) <= request.weight_grams <= Decimal(100000):
                    raise CarbonError("WEIGHT_INVALID")
        except CarbonError as exc:
            fail(exc.code)
        hash_payload = dict(payload)
        hash_payload["materials"] = {k: canonical_decimal(v) for k, v in request.materials.items()}
        hash_payload["weight_grams"] = (canonical_decimal(request.weight_grams)
                                          if request.weight_grams is not None else None)
        request_hash = hashlib.sha256(encode(hash_payload).encode()).hexdigest()
        def existing():
            return db.query(database.AnalysisResult).filter_by(
                user_id=user.id, client_request_id=request_key).first()
        if request_key is not None:
            previous = existing()
            if previous:
                return replay(previous, request_hash)
        if request.composition_scope != "single":
            fail("COMPOSITION_SCOPE_UNSUPPORTED")
        option = next((o for o in clothing_options if o["id"] == request.clothing_type_id), None)
        if request.clothing_type_id is not None and option is None:
            fail("CLOTHING_TYPE_INVALID")
        if request.weight_grams is not None:
            representative = minimum = maximum = request.weight_grams
            weight_source, catalog_version = "direct", None
        elif option:
            representative = Decimal(str(option["estimated_weight_grams"]))
            minimum = Decimal(str(option["min_weight_grams"]))
            maximum = Decimal(str(option["max_weight_grams"]))
            weight_source, catalog_version = "catalog", "legacy-placeholder-v1"
        else:
            fail("WEIGHT_MISSING", 400)
        profiles = db.query(database.CalculationProfile).filter_by(
            status="active", usage_scope=(
                "research_scenario" if os.getenv("K_DPP_CARBON_USAGE_SCOPE") == "research_scenario"
                else "public_estimate")).all()
        if len(profiles) != 1:
            fail("CALCULATION_PROFILE_UNAVAILABLE", 503)
        profile = profiles[0]
        if profile.scope != "fiber_production_estimate":
            fail("CALCULATION_PROFILE_INVALID", 503)
        materials = db.query(database.Material).all()
        by_name = {m.name_en: m for m in materials}
        aliases = {}
        for material in materials:
            for alias in [material.name_en, material.name_ko, *json.loads(material.aliases)]:
                key = alias.strip().lower()
                if key in aliases and aliases[key] != material.name_en:
                    fail("MATERIAL_CATALOG_AMBIGUOUS", 503)
                aliases[key] = material.name_en
        try:
            ratios = normalize(request.materials, aliases)
            factors = resolve_factors(db, profile.id, [by_name[name].id for name in ratios])
            calculated = calculate(request.materials, aliases,
                {name: factor["value"] for name, factor in factors.items()},
                representative, minimum, maximum)
        except CarbonError as exc:
            details = ({"unknown_materials": [name for name, ratio in request.materials.items()
                        if ratio > 0 and name.strip().lower() not in aliases]}
                       if exc.code == "MATERIAL_NOT_FOUND" else {})
            fail(exc.code, 400 if exc.code == "MATERIAL_NOT_FOUND" else 422, **details)
        factor_snapshots = []
        for name, details in factors.items():
            link = db.get(database.ProfileFactor, (profile.id, by_name[name].id))
            factor = db.get(database.MaterialFactor, link.factor_id)
            metadata = {column.name: getattr(factor, column.name)
                        for column in database.MaterialFactor.__table__.columns}
            factor_snapshots.append({**metadata, "standard_name": name,
                "ratio": str(ratios[name]), "selection_assumption": details["assumption"]})
        display = calculated["display"]
        response = {
            "status": "success", "message": "소재 생산 단계 탄소배출 추정 완료",
            "materials": {k: float(v) for k, v in request.materials.items()},
            "carbon_factor": float(calculated["mixed_factor"]),
            "carbon_footprint": float(display["representative"]),
            "average_carbon_footprint": float(display["representative"]),
            "carbon_footprint_min": float(display["min"]), "carbon_footprint_max": float(display["max"]),
            "min_weight_grams": float(minimum), "max_weight_grams": float(maximum),
            "representative_weight_grams": float(representative),
            "weight_grams": float(request.weight_grams) if request.weight_grams is not None else None,
            "weight_source": weight_source, "weight_evidence_type": "user_reported" if weight_source == "direct" else "placeholder",
            "clothing_type_id": request.clothing_type_id,
            "unit": "kg CO2eq", "source": "backend", "result_kind": "garment_estimate",
            "formula_version": calculated["formula_version"], "profile_version": profile.version,
            "usage_scope": profile.usage_scope,
            "value_basis": "representative_weight_not_statistical_average",
            "research_only": profile.usage_scope == "research_scenario",
            "calculation_scope": profile.scope, "provenance_status": "available",
            "assumptions": ["total_garment_mass_as_fiber_proxy"],
            "calculation_note": "총무게를 섬유 무게로 가정한 추정치입니다. 후속 제조·사용·폐기는 제외합니다.",
            "emission_factors": json.loads(encode(factor_snapshots)),
        }
        snapshot = {
            "schema_version": 1, "input": payload,
            "profile": {"id": profile.id, "key": profile.key, "version": profile.version,
                        "method": profile.method, "scope": profile.scope, "usage_scope": profile.usage_scope},
            "formula_version": calculated["formula_version"],
            "normalized_materials": calculated["ratios"],
            "factors": factor_snapshots, "results": calculated,
            "weight": {"source": weight_source, "representative_g": representative,
                       "min_g": minimum, "max_g": maximum, "catalog_version": catalog_version},
            "assumptions": response["assumptions"],
            "rounding": {"mode": "ROUND_HALF_UP", "decimal_places": 2},
            "response": response,
        }
        if profile.usage_scope == "research_scenario":
            response["calculation_note"] += " 연구용 문헌 시나리오이며 제품 인증·홍보·소재 간 우열 비교에 사용할 수 없습니다."
        # OCR remains in its existing column, not duplicated in the provenance document.
        snapshot["input"].pop("raw_ocr_text", None)
        result = database.AnalysisResult(user_id=user.id,
            materials=encode(response["materials"]), carbon_footprint=response["carbon_footprint"],
            carbon_footprint_min=response["carbon_footprint_min"],
            carbon_footprint_max=response["carbon_footprint_max"],
            min_weight_grams=float(minimum), max_weight_grams=float(maximum), unit="kg CO2eq",
            raw_ocr_text=request.raw_ocr_text, unknown_materials="[]", result_kind="garment_estimate",
            formula_version=calculated["formula_version"], profile_id=profile.id,
            snapshot_schema_version=1, calculation_snapshot_json=encode(snapshot),
            client_request_id=request_key, request_hash=request_hash)
        db.add(result)
        try:
            db.commit()
        except IntegrityError as error:
            db.rollback()
            if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "fk_analysis_results_user_id_users":
                raise HTTPException(401, detail="로그인이 만료되었습니다.") from None
            previous = existing() if request_key is not None else None
            if previous:
                return replay(previous, request_hash)
            raise
        except Exception:
            db.rollback()
            raise
        db.refresh(result)
        return {**response, "saved_result_id": result.id}
    return router
