"""Record loose artifact provenance; check retained bytes without modifying them."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/artifact-manifest.json"


def fingerprint(path: Path) -> dict:
    return {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def collect() -> list[dict]:
    groups = [
        (ROOT / "steadman/fonts", "bundled font asset; original font metadata preserved"),
        (
            ROOT / "docs/archive",
            "historical project source or handoff; not active application code",
        ),
        (ROOT / "output/legacy", "legacy generated PDF; source revision and settings unknown"),
        (ROOT / ".local-archive/outer-git", "inactive outer Git metadata; preserved local backup"),
    ]
    artifacts = []
    for directory, purpose in groups:
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.name != ".DS_Store" and "__pycache__" not in path.parts:
                artifacts.append(record(path, purpose))
    return artifacts


def record(path: Path, purpose: str) -> dict:
    import os

    artifact = {
        "path": os.path.relpath(path, ROOT),
        "location": "checkout",
        "tracking": "local-only"
        if path.is_relative_to(ROOT / "output") or path.is_relative_to(ROOT / ".local-archive")
        else "git",
        "purpose": purpose,
        **fingerprint(path),
    }
    plan_path = ROOT / "docs/archive/consolidation-plan.json"
    if plan_path.is_file():
        for move in json.loads(plan_path.read_text())["moves"]:
            destination = Path(move["destination"])
            relative = Path(artifact["path"])
            if relative == destination or destination in relative.parents:
                artifact["original_path"] = str(
                    Path(move["source"]) / relative.relative_to(destination)
                )
                break
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Verify existing inventory without rewriting it"
    )
    args = parser.parse_args()
    if args.check:
        artifacts = json.loads(MANIFEST.read_text())["artifacts"]
        failures, skipped = [], 0
        for artifact in artifacts:
            path = ROOT / artifact["path"]
            if not path.is_file() and artifact.get("tracking") == "local-only":
                group = ROOT / (
                    "output/legacy"
                    if artifact["path"].startswith("output/")
                    else ".local-archive/outer-git"
                )
                if not group.exists():
                    skipped += 1
                    continue
            if not path.is_file() or fingerprint(path) != {
                key: artifact[key] for key in ("bytes", "sha256")
            }:
                failures.append(artifact["path"])
        known = {artifact["path"] for artifact in artifacts}
        unexpected = {artifact["path"] for artifact in collect()} - known
        failures.extend(sorted(unexpected))
        if failures:
            raise SystemExit("Missing, changed, or unrecorded artifacts: " + ", ".join(failures))
        print(
            f"Verified {len(artifacts) - skipped} artifacts; {skipped} unavailable local-only artifacts skipped."
        )
    else:
        artifacts = collect()
        MANIFEST.write_text(
            json.dumps({"schema_version": 1, "artifacts": artifacts}, indent=2, ensure_ascii=False)
            + "\n"
        )
        print(f"Recorded {len(artifacts)} artifacts.")


if __name__ == "__main__":
    main()
