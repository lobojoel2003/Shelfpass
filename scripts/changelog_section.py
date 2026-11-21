#!/usr/bin/env python3
"""Print the CHANGELOG.md section for one version (used for GitHub release notes).

Usage: python scripts/changelog_section.py 1.0.0
Exits with status 1 if the version has no section, so a release can't ship
without notes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def section(version: str, text: str) -> str | None:
    pattern = re.compile(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|^\[[^\]]+\]: |\Z)", re.S | re.M
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    version = sys.argv[1].removeprefix("v")
    notes = section(version, CHANGELOG.read_text(encoding="utf-8"))
    if not notes:
        print(f"No CHANGELOG.md section for {version}", file=sys.stderr)
        return 1
    print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
