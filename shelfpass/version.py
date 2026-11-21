"""Version and build metadata.

The semantic version lives in :mod:`shelfpass` (``__version__``). Build
metadata (CI run number, commit, build date) is injected at build time, either
through environment variables or through a ``BUILD_INFO.json`` file that the
container build writes next to this module. Local checkouts report ``dev``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from shelfpass import __version__

_DEFAULT_BUILD_FILE = Path(__file__).resolve().parent / "BUILD_INFO.json"


@dataclass(frozen=True)
class BuildInfo:
    version: str
    build_number: str
    commit: str
    build_date: str

    @property
    def short_commit(self) -> str:
        return self.commit[:7] if self.commit and self.commit != "unknown" else self.commit

    @property
    def label(self) -> str:
        parts = [f"v{self.version}"]
        if self.build_number and self.build_number != "dev":
            parts.append(f"build {self.build_number}")
        else:
            parts.append("dev build")
        if self.commit and self.commit != "unknown":
            parts.append(self.short_commit)
        return " · ".join(parts)

    def as_dict(self) -> dict[str, str]:
        data = asdict(self)
        data["label"] = self.label
        return data


def _read_build_file(path: Path) -> dict[str, str]:
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items() if v not in (None, "")}


@lru_cache(maxsize=1)
def get_build_info() -> BuildInfo:
    file_data = _read_build_file(Path(os.environ.get("SHELFPASS_BUILD_INFO", _DEFAULT_BUILD_FILE)))

    def pick(env_name: str, key: str, default: str) -> str:
        return os.environ.get(env_name) or file_data.get(key) or default

    return BuildInfo(
        version=__version__,
        build_number=pick("SHELFPASS_BUILD_NUMBER", "build_number", "dev"),
        commit=pick("SHELFPASS_COMMIT", "commit", "unknown"),
        build_date=pick("SHELFPASS_BUILD_DATE", "build_date", "unknown"),
    )
