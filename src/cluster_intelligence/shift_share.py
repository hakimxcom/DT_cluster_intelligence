"""Classic three-component shift-share decomposition.

For industry i in region r between base year 0 and end year 1:

    national growth   NS = E0_ir * g_US
    industry mix      IM = E0_ir * (g_iUS - g_US)
    regional effect   RC = E0_ir * (g_ir - g_iUS)

where g are growth rates computed from the same ownership scope, industry
definitions and years. NS + IM + RC equals the observed change E1_ir - E0_ir."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .metrics import _valid

# Components are rounded to whole jobs on output; reconciliation is checked
# before rounding, so the tolerance only absorbs floating-point error.
RECONCILIATION_TOLERANCE = 1e-6


@dataclass(frozen=True)
class ShiftShare:
    base: float | None
    end: float | None
    observed_change: float | None
    national: float | None
    industry_mix: float | None
    regional: float | None
    status: str  # ok | missing_local | zero_base | missing_national | reconciliation_failed

    @property
    def residual(self) -> float | None:
        if self.status != "ok":
            return None
        return self.observed_change - (self.national + self.industry_mix + self.regional)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["residual"] = self.residual
        return d


def decompose(
    local_base: float | None,
    local_end: float | None,
    national_industry_base: float | None,
    national_industry_end: float | None,
    national_total_base: float | None,
    national_total_end: float | None,
    tolerance: float = RECONCILIATION_TOLERANCE,
) -> ShiftShare:
    if not _valid(local_base, local_end):
        return ShiftShare(local_base, local_end, None, None, None, None, "missing_local")
    observed = local_end - local_base
    if local_base <= 0:
        # Growth rates are undefined; no component can be attributed.
        return ShiftShare(local_base, local_end, observed, None, None, None, "zero_base")
    if not _valid(national_industry_base, national_industry_end, national_total_base, national_total_end) \
            or national_industry_base <= 0 or national_total_base <= 0:
        return ShiftShare(local_base, local_end, observed, None, None, None, "missing_national")

    g_us = national_total_end / national_total_base - 1
    g_i = national_industry_end / national_industry_base - 1
    g_ir = local_end / local_base - 1
    ns = local_base * g_us
    im = local_base * (g_i - g_us)
    rc = local_base * (g_ir - g_i)
    residual = observed - (ns + im + rc)
    scale = max(1.0, abs(local_base))
    status = "ok" if abs(residual) <= tolerance * scale else "reconciliation_failed"
    return ShiftShare(local_base, local_end, observed, ns, im, rc, status)
