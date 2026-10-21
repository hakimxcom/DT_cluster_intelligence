"""Build processed tables and the website dataset from data/raw.

    python scripts/build_dataset.py              # all years present in data/raw
    python scripts/build_dataset.py --start 2015 --end 2024

Writes data/processed/*.csv and data/processed/website/ (the exact files the
dashboard reads). Exits 1 if any validation check fails."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cluster_intelligence.build import Builder  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--start", type=int, default=2010)
    ap.add_argument("--end", type=int, default=2030)
    args = ap.parse_args()
    m = Builder(args.raw, args.out, list(range(args.start, args.end + 1))).run()
    print(f"status: {m['status']}  years: {m['years'][:1] + m['years'][-1:] if m['years'] else 'none'}  version: {m['dataset_version']}")
    for c in m["validation"]:
        print(f"  [{'pass' if c['passed'] else 'FAIL'}] {c['check']}: {c['detail']}")
    for s in m["sources"]:
        print(f"  source {s['id']:16} {s['status']}" + (f" — {s['reason']}" if s.get("reason") else ""))
    return 0 if m["status"] in ("complete", "no_data") else 1


if __name__ == "__main__":
    sys.exit(main())
