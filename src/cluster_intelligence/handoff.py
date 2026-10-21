"""Checksum-verified handoff of the website dataset to the website repository."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .sources import sha256

WEBSITE_SUBDIR = Path("public") / "data" / "cluster-dashboard"


def verify(directory: Path) -> dict:
    """Return the manifest if every listed file exists with the recorded checksum,
    and no unlisted JSON file is present."""
    directory = Path(directory)
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"{manifest_path} not found; run scripts/build_dataset.py first")
    manifest = json.loads(manifest_path.read_text())
    for name, meta in manifest["files"].items():
        path = directory / name
        if not path.exists():
            raise ValueError(f"{name} listed in the manifest is missing")
        if sha256(path) != meta["sha256"]:
            raise ValueError(f"{name} does not match its manifest checksum")
    listed = set(manifest["files"]) | {"manifest.json"}
    extra = {p.relative_to(directory).as_posix() for p in directory.rglob("*.json")} - listed
    if extra:
        raise ValueError(f"unlisted files in {directory}: {sorted(extra)}")
    return manifest


def export(source: Path, website_repo: Path) -> Path:
    website_repo = Path(website_repo)
    if not (website_repo / "public").is_dir() or not (website_repo / "wrangler.jsonc").exists():
        raise ValueError(f"{website_repo} does not look like the hakimxcom website repository")
    manifest = verify(source)
    if manifest["status"] == "failed_validation":
        raise ValueError("refusing to export a dataset that failed validation")
    dest = website_repo / WEBSITE_SUBDIR
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest)
    verify(dest)
    return dest
