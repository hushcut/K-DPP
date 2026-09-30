"""Pure calculation: no database or HTTP dependency."""
from decimal import Decimal, InvalidOperation, localcontext, ROUND_HALF_UP


class CarbonError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def number(value, code):
    if isinstance(value, bool):
        raise CarbonError(code)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise CarbonError(code) from None
    # Bound representation and magnitude, not a claim about physical clothing limits.
    if (not result.is_finite() or len(result.as_tuple().digits) > 40
            or abs(result.as_tuple().exponent) > 100):
        raise CarbonError(code)
    if result != 0 and not Decimal("1e-12") <= abs(result) <= Decimal("1e12"):
        raise CarbonError(code)
    return result


def normalize(materials, aliases):
    """aliases maps trimmed, lowercase input names to canonical names."""
    if not materials:
        raise CarbonError("MATERIAL_MISSING")
    merged = {}
    total = Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 80
        for name, raw in materials.items():
            ratio = number(raw, "MATERIAL_RATIO_INVALID")
            if ratio < 0:
                raise CarbonError("MATERIAL_RATIO_INVALID")
            total += ratio
            if ratio == 0:
                continue
            canonical = aliases.get(name.strip().lower())
            if canonical is None:
                raise CarbonError("MATERIAL_NOT_FOUND")
            merged[canonical] = merged.get(canonical, Decimal(0)) + ratio
        if not Decimal("99.5") <= total <= Decimal("100.5"):
            raise CarbonError("MATERIAL_RATIO_INVALID")
        return {name: ratio / total for name, ratio in merged.items()}


def calculate(materials, aliases, factors, representative_g, min_g, max_g):
    with localcontext() as ctx:
        ctx.prec = 80
        ratios = normalize(materials, aliases)
        weights = [number(v, "WEIGHT_INVALID") for v in (representative_g, min_g, max_g)]
        representative, minimum, maximum = weights
        if any(v <= 0 for v in weights):
            raise CarbonError("WEIGHT_INVALID")
        if not minimum <= representative <= maximum:
            raise CarbonError("WEIGHT_RANGE_INVALID")
        mixed = Decimal(0)
        for name, ratio in ratios.items():
            if name not in factors:
                raise CarbonError("FACTOR_UNAVAILABLE")
            factor = number(factors[name], "FACTOR_INVALID")
            if factor < 0:
                raise CarbonError("FACTOR_INVALID")
            mixed += ratio * factor
        raw = [mixed * weight / 1000 for weight in weights]
        return {
            "formula_version": "fiber_mass_v2",
            "ratios": ratios, "mixed_factor": mixed,
            "raw": dict(zip(("representative", "min", "max"), raw)),
            "display": dict(zip(("representative", "min", "max"),
                               [v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for v in raw])),
        }
