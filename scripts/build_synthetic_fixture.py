"""Build the SYNTHETIC test dataset used by the website's browser tests.

    python scripts/build_synthetic_fixture.py --out /tmp/cd-fixture

Writes invented numbers to <out>/raw and <out>/out/website. The manifest is
tagged synthetic_fixture=true, the export command refuses it, and the
dashboard labels it as test data if it is ever loaded. Never copy it into
the website repository."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from cluster_intelligence.build import Builder  # noqa: E402
from tests.fixtures import synthetic_raw  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if (args.out / "public").exists() or (args.out / "wrangler.jsonc").exists():
        raise SystemExit("refusing to write synthetic data into a website repository")
    synthetic_raw.build(args.out / "raw")
    m = Builder(args.out / "raw", args.out / "out", synthetic_raw.YEARS, external_dir=args.out / "none", synthetic=True).run()
    print(f"synthetic fixture: {args.out / 'out' / 'website'} (status {m['status']})")


if __name__ == "__main__":
    main()
