"""Read-only policy resolution. Candidate factors never become defaults."""
import os

import database
from .domain import CarbonError, number


def active_profiles(session):
    """Active profiles of the usage scope the V2 API calculates with (exactly one is usable)."""
    usage_scope = ("research_scenario" if os.getenv("K_DPP_CARBON_USAGE_SCOPE") == "research_scenario"
                   else "public_estimate")
    return session.query(database.CalculationProfile).filter_by(
        status="active", usage_scope=usage_scope).all()


def active_profile_material_ids(session):
    """Material ids the V2 API has a factor for, or None when no single active profile exists.

    The scan uses this for `is_supported` so that a material shown as supported before saving is
    one the V2 calculation accepts. Without an active profile every V2 save fails with 503 anyway,
    so callers fall back to catalog membership instead of flagging every material.
    """
    profiles = active_profiles(session)
    if len(profiles) != 1:
        return None
    return {link.material_id for link in session.query(database.ProfileFactor).filter_by(
        profile_id=profiles[0].id)}


def resolve_factors(session, profile_id, material_ids):
    profile = session.get(database.CalculationProfile, profile_id)
    if profile is None or profile.status != "active":
        raise CarbonError("CALCULATION_PROFILE_UNAVAILABLE")
    if profile.formula_version != "fiber_mass_v2":
        raise CarbonError("CALCULATION_PROFILE_INVALID")
    resolved = {}
    for material_id in set(material_ids):
        link = session.get(database.ProfileFactor, (profile.id, material_id))
        factor = session.get(database.MaterialFactor, link.factor_id) if link else None
        material = session.get(database.Material, material_id)
        if factor is None or material is None or factor.review_status != "selected":
            raise CarbonError("FACTOR_UNAVAILABLE")
        if (factor.material_id != material_id
                or factor.unit != "kg CO2eq/kg fiber"
                or factor.method != profile.method or factor.scope != profile.scope
                or factor.usage_scope != profile.usage_scope
                or factor.evidence_type not in ("literature", "derived")
                or not link.selection_assumption.strip()):
            raise CarbonError("FACTOR_INCOMPATIBLE")
        value = number(factor.value_decimal, "FACTOR_INVALID")
        if value < 0:
            raise CarbonError("FACTOR_INVALID")
        resolved[material.name_en] = {
            "value": value, "factor_key": factor.factor_key, "version": factor.version,
            "source_name": factor.source_name, "source_url": factor.source_url,
            "source_locator": factor.source_locator, "unit": factor.unit,
            "method": factor.method, "scope": factor.scope,
            "assumption": link.selection_assumption,
        }
    return resolved
