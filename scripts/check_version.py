#!/usr/bin/env python3
"""Fail unless a git tag (e.g. v1.2.3) matches shelfpass.__version__ and the changelog.

Usage: python scripts/check_version.py v1.2.3
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else ""
    version = tag.removeprefix("v")
    init = (ROOT / "shelfpass" / "__init__.py").read_text(encoding="utf-8")
    declared = re.search(r'__version__ = "([^"]+)"', init).group(1)
    problems = []
    if not SEMVER.match(version):
        problems.append(f"tag {tag!r} is not v<MAJOR>.<MINOR>.<PATCH>")
    if version != declared:
        problems.append(f"tag {tag!r} does not match shelfpass.__version__ = {declared!r}")
    if f"## [{version}]" not in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"):
        problems.append(f"CHANGELOG.md has no '## [{version}]' section")
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    if not problems:
        print(f"Version {version} is consistent.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
