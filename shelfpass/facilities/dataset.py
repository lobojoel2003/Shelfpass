"""Load, validate, import and export the open facility-rules dataset.

Layout (see ``dataset/README.md``)::

    dataset/
      dataset.json                  metadata (name, version, licence)
      schema/dataset.schema.json    JSON Schema for every file below
      jurisdictions/*.json          system-wide rules (a state DOC, the BOP)
      facilities/<state>/*.json     one file per facility
      rejections/*.json             anonymised rejection reports
      sample/...                    fictional records for demos and tests
"""

from __future__ import annotations

import datetime
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.db import transaction
from jsonschema import Draft202012Validator

from shelfpass.core.text import normalize_isbn
from shelfpass.facilities.models import Facility, Jurisdiction, Origin, RejectionReport

SCHEMA_PATH = Path("schema") / "dataset.schema.json"
KINDS = ("jurisdiction", "facility", "rejections")
FOLDERS = {"jurisdiction": "jurisdictions", "facility": "facilities", "rejections": "rejections"}


class DatasetError(Exception):
    pass


@dataclass
class Record:
    kind: str
    path: str  # relative to the dataset root, POSIX style
    data: dict
    sample: bool


@dataclass
class Dataset:
    root: Path
    meta: dict = field(default_factory=dict)
    records: list[Record] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def of_kind(self, kind: str, include_samples: bool = False) -> list[Record]:
        return [r for r in self.records if r.kind == kind and (include_samples or not r.sample)]

    @property
    def version(self) -> str:
        return str(self.meta.get("version", "unknown"))

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    retired: int = 0
    rejections: int = 0

    def __str__(self) -> str:
        return (
            f"{self.created} created, {self.updated} updated, {self.unchanged} unchanged, "
            f"{self.retired} retired, {self.rejections} rejection reports"
        )


def dataset_root() -> Path:
    return Path(settings.SHELFPASS["DATASET_DIR"])


def load_schema(root: Path) -> dict:
    path = root / SCHEMA_PATH
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DatasetError(f"Cannot read schema {path}: {exc}") from exc


def validator_for(schema: dict, kind: str) -> Draft202012Validator:
    wrapper = {
        "$schema": schema.get("$schema", "https://json-schema.org/draft/2020-12/schema"),
        "$defs": schema["$defs"],
        "$ref": f"#/$defs/{kind}",
    }
    return Draft202012Validator(wrapper)


def _iter_files(root: Path, sub: str) -> Iterable[Path]:
    base = root / sub
    if base.is_dir():
        yield from sorted(p for p in base.rglob("*.json") if p.is_file())


def load_dataset(root: Path | None = None) -> Dataset:
    """Read and validate every file. Problems are collected, not raised."""
    root = Path(root or dataset_root())
    if not root.is_dir():
        raise DatasetError(f"Dataset directory not found: {root}")
    schema = load_schema(root)
    validators = {kind: validator_for(schema, kind) for kind in KINDS}
    dataset = Dataset(root=root)

    meta_path = root / "dataset.json"
    if meta_path.exists():
        try:
            dataset.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            dataset.errors.append(f"dataset.json: invalid JSON ({exc})")

    for sample in (False, True):
        prefix = "sample/" if sample else ""
        for kind in KINDS:
            for path in _iter_files(root, prefix + FOLDERS[kind]):
                rel = path.relative_to(root).as_posix()
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except ValueError as exc:
                    dataset.errors.append(f"{rel}: invalid JSON ({exc})")
                    continue
                problems = sorted(validators[kind].iter_errors(data), key=lambda e: list(e.path))
                for problem in problems:
                    where = "/".join(str(p) for p in problem.absolute_path) or "(root)"
                    dataset.errors.append(f"{rel}: {where}: {problem.message}")
                if problems:
                    continue
                if kind != "rejections" and bool(data.get("sample")) != sample:
                    dataset.errors.append(
                        f'{rel}: records under sample/ must set "sample": true, and only they may'
                    )
                    continue
                dataset.records.append(Record(kind, rel, data, sample))

    _cross_check(dataset)
    return dataset


def _cross_check(dataset: Dataset) -> None:
    seen: dict[tuple[str, str], str] = {}
    for record in dataset.records:
        if record.kind == "rejections":
            continue
        key = (record.kind, record.data["id"])
        if key in seen:
            dataset.errors.append(f"{record.path}: duplicate id {key[1]!r} (also in {seen[key]})")
        seen[key] = record.path

    jurisdictions = {r.data["id"]: r for r in dataset.records if r.kind == "jurisdiction"}
    facilities = {r.data["id"]: r for r in dataset.records if r.kind == "facility"}
    for record in dataset.records:
        if record.kind == "facility":
            ref = record.data.get("jurisdiction")
            if ref and ref not in jurisdictions:
                dataset.errors.append(f"{record.path}: unknown jurisdiction {ref!r}")
            elif ref and jurisdictions[ref].sample and not record.sample:
                dataset.errors.append(f"{record.path}: real facility points at sample jurisdiction")
            state = record.data["address"]["state"]
            folder = record.path.split("/")[-2]
            if folder.upper() != state:
                dataset.errors.append(
                    f"{record.path}: facility in {state} must live in a folder named {state.lower()}/"
                )
        elif record.kind == "rejections":
            for index, report in enumerate(record.data["reports"]):
                if report["facility"] not in facilities:
                    dataset.errors.append(
                        f"{record.path}: reports/{index}: unknown facility {report['facility']!r}"
                    )


# ------------------------------------------------------------------ import ---


def _parse_date(value: str | None) -> datetime.date | None:
    return datetime.date.fromisoformat(value) if value else None


def _apply(obj, values: dict) -> bool:
    changed = False
    for key, value in values.items():
        if getattr(obj, key) != value:
            setattr(obj, key, value)
            changed = True
    return changed


def sync_dataset(dataset: Dataset, include_samples: bool = False) -> SyncResult:
    """Upsert dataset records into the database. Local records are never touched."""
    if not dataset.is_valid:
        raise DatasetError("Refusing to import an invalid dataset:\n" + "\n".join(dataset.errors))
    with transaction.atomic():
        return _sync(dataset, include_samples)


def _sync(dataset: Dataset, include_samples: bool) -> SyncResult:
    result = SyncResult()

    jurisdictions: dict[str, Jurisdiction] = {}
    for record in dataset.of_kind("jurisdiction", include_samples):
        data = record.data
        values = {
            "name": data["name"],
            "kind": data["kind"],
            "state": data.get("state", ""),
            "rules": data.get("rules", {}),
            "sources": data.get("sources", []),
            "last_verified": _parse_date(data.get("last_verified")),
            "origin": Origin.DATASET,
            "is_sample": record.sample,
            "dataset_path": record.path,
        }
        obj = Jurisdiction.objects.filter(code=data["id"]).first()
        if obj is None:
            obj = Jurisdiction.objects.create(code=data["id"], **values)
            result.created += 1
        elif _apply(obj, values):
            obj.save()
            result.updated += 1
        else:
            result.unchanged += 1
        jurisdictions[obj.code] = obj

    seen_slugs: set[str] = set()
    for record in dataset.of_kind("facility", include_samples):
        data = record.data
        address = data["address"]
        jurisdiction = jurisdictions.get(data.get("jurisdiction", ""))
        if jurisdiction is None and data.get("jurisdiction"):
            jurisdiction = Jurisdiction.objects.filter(code=data["jurisdiction"]).first()
        values = {
            "name": data["name"],
            "kind": data["kind"],
            "jurisdiction": jurisdiction,
            "street": "\n".join(address["street"]),
            "city": address["city"],
            "state": address["state"],
            "postal_code": address["postal_code"],
            "phone": data.get("phone", ""),
            "website": data.get("website", ""),
            "notes": data.get("notes", ""),
            "rules": data.get("rules", {}),
            "sources": data.get("sources", []),
            "last_verified": _parse_date(data.get("last_verified")),
            "active": data.get("active", True),
            "origin": Origin.DATASET,
            "is_sample": record.sample,
            "dataset_path": record.path,
        }
        seen_slugs.add(data["id"])
        obj = Facility.objects.filter(slug=data["id"]).first()
        if obj is None:
            Facility.objects.create(slug=data["id"], **values)
            result.created += 1
        elif obj.origin == Origin.LOCAL:
            # A volunteer created a local facility with this slug before it was
            # contributed; adopt the dataset version so groups converge.
            _apply(obj, values)
            obj.save()
            result.updated += 1
        elif _apply(obj, values):
            obj.save()
            result.updated += 1
        else:
            result.unchanged += 1

    stale = Facility.objects.filter(origin=Origin.DATASET, active=True).exclude(slug__in=seen_slugs)
    if not include_samples:
        stale = stale.filter(is_sample=False)
    result.retired = stale.update(active=False)

    result.rejections = _sync_rejections(dataset, include_samples)
    return result


def report_id(path: str, report: dict) -> str:
    blob = json.dumps({"path": path, **report}, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:40]


def _sync_rejections(dataset: Dataset, include_samples: bool) -> int:
    facilities = {f.slug: f for f in Facility.objects.filter(origin=Origin.DATASET)}
    keep: set[str] = set()
    for record in dataset.of_kind("rejections", include_samples):
        reporter = record.data.get("reporter", "")
        for report in record.data["reports"]:
            facility = facilities.get(report["facility"])
            if facility is None:
                continue
            external_id = report_id(record.path, report)
            keep.add(external_id)
            book = report.get("book", {})
            year, month = (int(x) for x in report["month"].split("-"))
            RejectionReport.objects.update_or_create(
                external_id=external_id,
                defaults={
                    "facility": facility,
                    "month": datetime.date(year, month, 1),
                    "reason": report["reason"],
                    "title": book.get("title", ""),
                    "authors": book.get("authors", ""),
                    "isbn": normalize_isbn(book.get("isbn", "")),
                    "format": book.get("format", ""),
                    "condition": book.get("condition", ""),
                    "detail": report.get("detail", "")[:500],
                    "reporter": reporter,
                    "dataset_path": record.path,
                },
            )
    RejectionReport.objects.exclude(external_id__in=keep).delete()
    return len(keep)


# ------------------------------------------------------------------ export ---


def _clean(data: dict) -> dict:
    return {k: v for k, v in data.items() if v not in ("", None, [], {})}


def facility_to_dataset(facility: Facility) -> dict:
    """The facility as a dataset file, ready to open as a pull request."""
    data = {
        "id": facility.slug,
        "name": facility.name,
        "kind": facility.kind,
        "jurisdiction": facility.jurisdiction.code if facility.jurisdiction_id else "",
        "address": {
            "street": [line.strip() for line in facility.street.splitlines() if line.strip()],
            "city": facility.city,
            "state": facility.state,
            "postal_code": facility.postal_code,
        },
        "phone": facility.phone,
        "website": facility.website,
        "rules": _clean(dict(facility.rules or {})),
        "notes": facility.notes,
        "sources": list(facility.sources or []),
        "last_verified": facility.last_verified.isoformat() if facility.last_verified else "",
    }
    if facility.is_sample:
        data["sample"] = True
    if not facility.active:
        data["active"] = False
    return _clean(data)


def facility_dataset_path(facility: Facility) -> str:
    prefix = "sample/" if facility.is_sample else ""
    return f"{prefix}facilities/{facility.state.lower()}/{facility.slug}.json"


def dumps(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
