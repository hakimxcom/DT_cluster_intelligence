"""Location quotients, employment growth and employment shares.

Every function returns ``None`` when an input is missing, suppressed or would
make the measure undefined. Missing values are never treated as zero."""
from __future__ import annotations

import math
from dataclasses import dataclass


def _valid(*values) -> bool:
    return all(v is not None and not (isinstance(v, float) and math.isnan(v)) for v in values)


def share(part: float | None, total: float | None) -> float | None:
    """Employment share part/total; undefined for a missing or non-positive total."""
    if not _valid(part, total) or total <= 0 or part < 0:
        return None
    return part / total


def location_quotient(
    local_industry: float | None,
    local_total: float | None,
    national_industry: float | None,
    national_total: float | None,
) -> float | None:
    """LQ = (E_ir / E_r) / (E_iUS / E_US).

    All four inputs must come from the same year and ownership scope. Returns
    None when any input is missing or when a denominator is not positive."""
    local_share = share(local_industry, local_total)
    national_share = share(national_industry, national_total)
    if local_share is None or national_share is None or national_share == 0:
        return None
    return local_share / national_share


@dataclass(frozen=True)
class Growth:
    start: float | None
    end: float | None
    change: float | None
    pct: float | None  # fraction, e.g. 0.05 for 5%

    @property
    def status(self) -> str:
        if self.change is None:
            return "missing"
        if self.pct is None:
            return "zero_base"
        return "ok"


def growth(start: float | None, end: float | None) -> Growth:
    """Absolute and percentage change between two observations.

    Absolute change is reported whenever both values exist. Percentage change
    is withheld when the base is zero or negative, because it is undefined."""
    if not _valid(start, end):
        return Growth(start, end, None, None)
    change = end - start
    pct = change / start if start > 0 else None
    return Growth(start, end, change, pct)
