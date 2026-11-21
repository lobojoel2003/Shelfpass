#!/usr/bin/env python3
"""Build the release bundle of the open dataset.

Writes ``<out>/shelfpass-dataset-<version>.zip`` containing the raw dataset
files (samples excluded) plus merged ``jurisdictions.json``, ``facilities.json``
and ``rejections.json``. Run ``manage.py sync_dataset --check`` first: this
script assumes the files are valid.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "dataset"


def load_all(folder: Path) -> list[dict]:
    if not folder.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.rglob("*.json"))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("dist"))
    parser.add_argument("--dataset", type=Path, default=ROOT)
    args = parser.parse_args()

    meta = json.loads((args.dataset / "dataset.json").read_text(encoding="utf-8"))
    version = meta["version"]
    merged = {
        "jurisdictions.json": load_all(args.dataset / "jurisdictions"),
        "facilities.json": load_all(args.dataset / "facilities"),
        "rejections.json": [
            {**report, "reporter": f.get("reporter", "")}
            for f in load_all(args.dataset / "rejections")
            for report in f["reports"]
        ],
    }

    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / f"shelfpass-dataset-{version}.zip"
    prefix = f"shelfpass-dataset-{version}/"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(args.dataset.rglob("*")):
            rel = path.relative_to(args.dataset)
            if path.is_file() and rel.parts[0] != "sample" and path.name != ".gitkeep":
                bundle.write(path, prefix + "raw/" + rel.as_posix())
        for name, data in merged.items():
            bundle.writestr(
                prefix + name, json.dumps({"version": version, "items": data}, indent=2) + "\n"
            )
        bundle.writestr(prefix + "LICENSE", (args.dataset / "LICENSE").read_text(encoding="utf-8"))
    counts = ", ".join(f"{len(v)} {k.removesuffix('.json')}" for k, v in merged.items())
    print(f"Wrote {target} ({counts})")


if __name__ == "__main__":
    main()
