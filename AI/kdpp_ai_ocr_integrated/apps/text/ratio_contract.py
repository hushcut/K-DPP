"""Exact composition totals, separate from QA measurement tolerance."""

from decimal import Decimal, InvalidOperation, localcontext
from typing import Iterable


EXACT_RATIO_TOTAL = Decimal("100")


def sum_ratios(values: Iterable[Decimal | int | float]) -> Decimal:
    ratios = [value if isinstance(value, Decimal) else Decimal(str(value)) for value in values]
    if not ratios or any(not value.is_finite() for value in ratios):
        return Decimal("NaN")
    fractional_digits = max(0, -min(value.as_tuple().exponent for value in ratios))
    integer_digits = max(3, *(value.adjusted() + 1 for value in ratios))
    with localcontext() as context:
        context.prec = integer_digits + len(str(len(ratios))) + fractional_digits + 1
        return sum(ratios, Decimal(0))


def has_exact_total(values: Iterable[Decimal | int | float]) -> bool:
    try:
        ratios = [value if isinstance(value, Decimal) else Decimal(str(value)) for value in values]
        return bool(ratios) and all(
            value.is_finite() and 0 < value <= EXACT_RATIO_TOTAL for value in ratios
        ) and sum_ratios(ratios) == EXACT_RATIO_TOTAL
    except (InvalidOperation, ValueError, TypeError):
        return False
