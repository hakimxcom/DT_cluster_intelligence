"""Hand the validated website dataset to the website repository.

    python scripts/export_to_website.py --website ../hakimxcom

Copies data/processed/website/ to <website>/public/data/cluster-dashboard/,
replacing what is there, after checking that the manifest exists, that its
status is not failed_validation, and that every file matches the checksum the
manifest recorded. The copied files are re-checked after the copy."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cluster_intelligence.handoff import export  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--website", type=Path, required=True, help="path to the hakimxcom repository")
    ap.add_argument("--source", type=Path, default=ROOT / "data" / "processed" / "website")
    args = ap.parse_args()
    dest = export(args.source, args.website)
    print(f"Exported {len(json.loads((dest / 'manifest.json').read_text())['files']) + 1} files to {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
