from decimal import Decimal
from types import SimpleNamespace
import pytest
import database
from carbon.domain import CarbonError, calculate, normalize
from carbon.factors import resolve_factors

ALIASES = {"cotton": "cotton", "면": "cotton", "polyester": "polyester"}


def test_alias_merge_and_zero_unknown():
    assert normalize({"면": 50, "cotton": 50, "unknown": 0}, ALIASES) == {"cotton": Decimal(1)}


@pytest.mark.parametrize("total", ["99.5", "100.5"])
def test_ratio_boundaries(total):
    assert normalize({"cotton": total}, ALIASES) == {"cotton": Decimal(1)}


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "99.49", "100.51", True, "1e1000"])
def test_invalid_ratios(value):
    with pytest.raises(CarbonError):
        normalize({"cotton": value}, ALIASES)


def test_hand_calculation_and_final_rounding():
    result = calculate({"cotton": 80, "polyester": 20}, ALIASES,
                       {"cotton": "8.3", "polyester": "9.5"}, 200, 100, 250)
    assert result["mixed_factor"] == Decimal("8.54")
    assert result["raw"]["representative"] == Decimal("1.708")
    assert result["display"] == {"representative": Decimal("1.71"),
                                 "min": Decimal("0.85"), "max": Decimal("2.14")}


def test_half_up_and_catalog_representative():
    result = calculate({"cotton": 100}, ALIASES, {"cotton": "8.3"}, 180, 100, 250)
    assert result["display"]["representative"] == Decimal("1.49")
    result = calculate({"cotton": 100}, ALIASES, {"cotton": "1"}, 5, 5, 5)
    assert result["display"]["representative"] == Decimal("0.01")


@pytest.mark.parametrize("weights", [(0, 0, 0), (100, 200, 300), ("NaN", 1, 2)])
def test_invalid_weight(weights):
    with pytest.raises(CarbonError):
        calculate({"cotton": 100}, ALIASES, {"cotton": 1}, *weights)


def test_missing_factor():
    with pytest.raises(CarbonError, match="FACTOR_UNAVAILABLE"):
        calculate({"cotton": 100}, ALIASES, {}, 100, 100, 100)


def policy_session(**changes):
    profile = SimpleNamespace(id=1, status="active", formula_version="fiber_mass_v2",
                              method="test", scope="test", usage_scope="research")
    factor = SimpleNamespace(material_id=2, review_status="selected",
        evidence_type="literature", unit="kg CO2eq/kg fiber", method="test", scope="test",
        usage_scope="research", value_decimal="1.23", factor_key="fixture", version="1",
        source_name="fixture", source_url="https://example.invalid", source_locator="table")
    for name, value in changes.items():
        setattr(factor, name, value)
    items = {database.CalculationProfile: profile, database.MaterialFactor: factor,
             database.ProfileFactor: SimpleNamespace(factor_id=3, selection_assumption="test case"),
             database.Material: SimpleNamespace(name_en="cotton")}
    return SimpleNamespace(get=lambda model, key: items[model])


def test_selected_factor_is_resolved():
    assert resolve_factors(policy_session(), 1, [2])["cotton"]["value"] == Decimal("1.23")


@pytest.mark.parametrize("changes", [
    {"review_status": "candidate"}, {"material_id": 9}, {"method": "other"},
    {"scope": "other"}, {"usage_scope": "commercial"}, {"unit": "kg"},
    {"evidence_type": "placeholder"}, {"value_decimal": "NaN"}])
def test_ineligible_factor_rejected(changes):
    with pytest.raises(CarbonError):
        resolve_factors(policy_session(**changes), 1, [2])
