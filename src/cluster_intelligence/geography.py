"""Metropolitan and state geography: loading, consistency checks, and
verification against the official OMB/Census delineation file."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GEOGRAPHY_FILE = ROOT / "config" / "geography.json"


@dataclass(frozen=True)
class Metro:
    id: str
    label: str
    cbsa_code: str
    cbsa_title: str
    qcew_area: str
    states: tuple[str, ...]
    counties: dict[str, str] = field(hash=False)
    boundary_note: str = ""
    # (area, last_year) pairs for QCEW codes BLS used before the current one.
    previous_qcew_areas: tuple[tuple[str, int], ...] = ()

    @property
    def county_fips(self) -> list[str]:
        return sorted(self.counties)

    @property
    def qcew_areas(self) -> list[str]:
        return [self.qcew_area] + [a for a, _ in self.previous_qcew_areas]

    def qcew_area_for(self, year: int) -> str:
        """The QCEW metro code BLS published for ``year``."""
        for area, last_year in sorted(self.previous_qcew_areas, key=lambda p: p[1]):
            if year <= last_year:
                return area
        return self.qcew_area


def load_config(path: Path = GEOGRAPHY_FILE) -> dict:
    return json.loads(Path(path).read_text())


def load_metros(path: Path = GEOGRAPHY_FILE) -> list[Metro]:
    cfg = load_config(path)
    metros = [
        Metro(
            id=m["id"], label=m["label"], cbsa_code=m["cbsa_code"],
            cbsa_title=m["cbsa_title"], qcew_area=m["qcew_area"],
            states=tuple(m["states"]), counties=dict(m["counties"]),
            boundary_note=m.get("boundary_note", ""),
            previous_qcew_areas=tuple((p["area"], int(p["last_year"])) for p in m.get("previous_qcew_areas", [])),
        )
        for m in cfg["metros"]
    ]
    check_internal_consistency(metros)
    return metros


def check_internal_consistency(metros: list[Metro]) -> None:
    """Fail on malformed FIPS codes, counties outside the metro's states, or a
    county assigned to more than one metro (which would double count)."""
    state_fips = {"MI": "26", "IL": "17", "IN": "18", "OH": "39"}
    seen: dict[str, str] = {}
    for m in metros:
        if not (len(m.cbsa_code) == 5 and m.cbsa_code.isdigit()):
            raise ValueError(f"{m.id}: CBSA code {m.cbsa_code!r} is not 5 digits")
        if m.qcew_area != "C" + m.cbsa_code[:4]:
            raise ValueError(f"{m.id}: QCEW area {m.qcew_area} does not match CBSA {m.cbsa_code}")
        for area, _ in m.previous_qcew_areas:
            if not (len(area) == 5 and area[0] == "C" and area[1:].isdigit()):
                raise ValueError(f"{m.id}: previous QCEW area {area!r} is not a C#### metro code")
        allowed = {state_fips[s] for s in m.states}
        for fips in m.counties:
            if not (len(fips) == 5 and fips.isdigit()):
                raise ValueError(f"{m.id}: county FIPS {fips!r} is not 5 digits")
            if fips[:2] not in allowed:
                raise ValueError(f"{m.id}: county {fips} is outside {m.states}")
            if fips in seen:
                raise ValueError(f"county {fips} assigned to both {seen[fips]} and {m.id}")
            seen[fips] = m.id


def read_delineation_file(path: Path) -> pd.DataFrame:
    """Read the Census 'list1' delineation workbook.

    The workbook has title rows above the header, so the header row is found by
    looking for the 'CBSA Code' cell rather than assuming a fixed offset."""
    raw = pd.read_excel(path, header=None, dtype=str)
    header_rows = raw.index[raw.apply(lambda r: r.astype(str).str.strip().eq("CBSA Code").any(), axis=1)]
    if len(header_rows) == 0:
        raise ValueError(f"{path}: no 'CBSA Code' header row found")
    h = header_rows[0]
    df = raw.iloc[h + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[h]]
    df = df.dropna(subset=["CBSA Code"])
    df = df[df["CBSA Code"].str.strip().str.fullmatch(r"\d{5}")]
    df["county_fips"] = df["FIPS State Code"].str.zfill(2) + df["FIPS County Code"].str.zfill(3)
    return df


def verify_against_delineation(metros: list[Metro], delineation: pd.DataFrame) -> list[str]:
    """Return a list of discrepancies (empty when every metro matches)."""
    problems = []
    for m in metros:
        rows = delineation[delineation["CBSA Code"].str.strip() == m.cbsa_code]
        if rows.empty:
            problems.append(f"{m.id}: CBSA {m.cbsa_code} not found in delineation file")
            continue
        title = rows["CBSA Title"].iloc[0].strip()
        if title != m.cbsa_title:
            problems.append(f"{m.id}: title {m.cbsa_title!r} differs from official {title!r}")
        kind = rows["Metropolitan/Micropolitan Statistical Area"].iloc[0]
        if "Metropolitan" not in str(kind):
            problems.append(f"{m.id}: CBSA {m.cbsa_code} is not a metropolitan statistical area")
        official = set(rows["county_fips"])
        ours = set(m.counties)
        if missing := sorted(official - ours):
            problems.append(f"{m.id}: missing official counties {missing}")
        if extra := sorted(ours - official):
            problems.append(f"{m.id}: counties not in the official CBSA {extra}")
    return problems
