"""Check config/geography.json against the official delineation file.

    python scripts/verify_geography.py

Reads data/raw/delineation/list1_2023.xlsx (downloaded by fetch_sources.py),
writes data/raw/delineation/verification.json, and exits non-zero on any
discrepancy so the result cannot be ignored."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cluster_intelligence.geography import load_metros, read_delineation_file, verify_against_delineation  # noqa: E402
from cluster_intelligence.sources import sha256  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "data" / "raw" / "delineation" / "list1_2023.xlsx"


def main() -> int:
    if not FILE.exists():
        print(f"Missing {FILE.relative_to(ROOT)}; run scripts/fetch_sources.py --only delineation first.")
        return 2
    problems = verify_against_delineation(load_metros(), read_delineation_file(FILE))
    result = {
        "status": "verified" if not problems else "mismatch",
        "problems": problems,
        "file": FILE.name,
        "sha256": sha256(FILE),
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (FILE.parent / "verification.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
