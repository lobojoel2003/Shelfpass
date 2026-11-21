from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from shelfpass.facilities import dataset as ds
from shelfpass.facilities.models import Facility, Jurisdiction, Origin, RejectionReport
from shelfpass.facilities.rules import RULE_KEYS
from shelfpass.facilities.vocab import (
    US_STATES,
    BookCondition,
    BookFormat,
    ContentCategory,
    FacilityKind,
    JurisdictionKind,
    RejectionReason,
)

REPO_DATASET = Path(__file__).resolve().parent.parent / "dataset"


@pytest.fixture
def schema():
    return ds.load_schema(REPO_DATASET)


@pytest.fixture
def tmp_dataset(tmp_path) -> Path:
    root = tmp_path / "dataset"
    shutil.copytree(REPO_DATASET, root)
    return root


def write(root: Path, rel: str, data: dict) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


FACILITY = {
    "id": "pa-example-sci",
    "name": "Example SCI",
    "kind": "state-prison",
    "address": {"street": ["1 Road"], "city": "Town", "state": "PA", "postal_code": "00001"},
    "rules": {"paperback_only": True},
}


# --------------------------------------------------- the shipped dataset ---


def test_repository_dataset_is_valid():
    dataset = ds.load_dataset(REPO_DATASET)
    assert dataset.errors == []
    assert dataset.version
    assert dataset.of_kind("jurisdiction")  # at least the federal BOP entry
    assert dataset.of_kind("facility", include_samples=True)


def test_vocabularies_match_schema(schema):
    defs = schema["$defs"]
    assert defs["rejection_reason"]["enum"] == RejectionReason.values
    assert defs["content_category"]["enum"] == ContentCategory.values
    assert defs["book_format"]["enum"] == BookFormat.values
    assert defs["book_condition"]["enum"] == BookCondition.values
    assert defs["facility"]["properties"]["kind"]["enum"] == FacilityKind.values
    assert defs["jurisdiction"]["properties"]["kind"]["enum"] == JurisdictionKind.values
    assert defs["state"]["enum"] == [code for code, _ in US_STATES]
    assert set(defs["rules"]["properties"]) == set(RULE_KEYS)


def test_samples_are_flagged_and_fictional():
    dataset = ds.load_dataset(REPO_DATASET)
    for record in dataset.records:
        if record.kind == "rejections":
            continue
        assert record.sample == record.path.startswith("sample/")
        if record.sample:
            assert record.data["id"].startswith("sample-")


# ----------------------------------------------------------- validation ---


def test_invalid_files_are_reported(tmp_dataset):
    write(
        tmp_dataset,
        "facilities/pa/broken.json",
        {**FACILITY, "id": "Bad ID", "rules": {"paperback_only": "yes"}},
    )
    (tmp_dataset / "facilities/pa/garbage.json").write_text("{not json", encoding="utf-8")
    write(tmp_dataset, "facilities/oh/pa-example-sci.json", FACILITY)  # wrong folder for PA
    write(tmp_dataset, "facilities/pa/dup.json", {**FACILITY, "jurisdiction": "missing-doc"})
    write(tmp_dataset, "facilities/pa/sneaky.json", {**FACILITY, "id": "pa-sneaky", "sample": True})
    write(
        tmp_dataset,
        "facilities/pa/real-on-sample.json",
        {**FACILITY, "id": "pa-real", "jurisdiction": "sample-northfield-doc"},
    )
    write(
        tmp_dataset,
        "rejections/bad.json",
        {"reports": [{"facility": "nowhere", "month": "2026-01", "reason": "content"}]},
    )
    (tmp_dataset / "dataset.json").write_text("{", encoding="utf-8")

    dataset = ds.load_dataset(tmp_dataset)
    text = "\n".join(dataset.errors)
    assert "broken.json: id" in text
    assert "rules/paperback_only" in text
    assert "garbage.json: invalid JSON" in text
    assert "must live in a folder named pa/" in text
    assert "unknown jurisdiction 'missing-doc'" in text
    assert "duplicate id 'pa-example-sci'" in text
    assert "sneaky.json: records under sample/" in text
    assert "real facility points at sample jurisdiction" in text
    assert "unknown facility 'nowhere'" in text
    assert "dataset.json: invalid JSON" in text
    with pytest.raises(ds.DatasetError):
        ds.sync_dataset(dataset)


def test_missing_directory_and_schema(tmp_path):
    with pytest.raises(ds.DatasetError):
        ds.load_dataset(tmp_path / "nope")
    (tmp_path / "empty").mkdir()
    with pytest.raises(ds.DatasetError):
        ds.load_dataset(tmp_path / "empty")


def test_local_prefix_is_reserved(schema):
    validator = ds.validator_for(schema, "facility")
    errors = list(validator.iter_errors({**FACILITY, "id": "local-pa-thing"}))
    assert errors


# --------------------------------------------------------------- import ---


@pytest.mark.django_db
def test_sync_creates_updates_and_retires(tmp_dataset):
    write(tmp_dataset, "facilities/pa/pa-example-sci.json", {**FACILITY, "jurisdiction": "us-bop"})
    result = ds.sync_dataset(ds.load_dataset(tmp_dataset))
    assert result.created == 2  # BOP + the facility; samples skipped
    facility = Facility.objects.get(slug="pa-example-sci")
    assert facility.origin == Origin.DATASET
    assert facility.jurisdiction.code == "us-bop"
    assert facility.ruleset.paperback_only and facility.ruleset.hardcover_vendor_only
    assert not Facility.objects.filter(is_sample=True).exists()

    again = ds.sync_dataset(ds.load_dataset(tmp_dataset))
    assert again.created == 0 and again.updated == 0 and again.unchanged == 2

    write(tmp_dataset, "facilities/pa/pa-example-sci.json", {**FACILITY, "name": "Renamed SCI"})
    assert ds.sync_dataset(ds.load_dataset(tmp_dataset)).updated == 1
    assert Facility.objects.get(slug="pa-example-sci").name == "Renamed SCI"

    (tmp_dataset / "facilities/pa/pa-example-sci.json").unlink()
    assert ds.sync_dataset(ds.load_dataset(tmp_dataset)).retired == 1
    assert not Facility.objects.get(slug="pa-example-sci").active


@pytest.mark.django_db
def test_sync_samples_and_rejections():
    result = ds.sync_dataset(ds.load_dataset(REPO_DATASET), include_samples=True)
    assert result.rejections == RejectionReport.objects.count() > 0
    assert Facility.objects.filter(is_sample=True, active=False).exists()  # the closed sample
    assert Jurisdiction.objects.filter(code="sample-northfield-doc", is_sample=True).exists()
    report = RejectionReport.objects.filter(title="The New Jim Crow").get()
    assert report.month.day == 1 and report.reporter

    # Re-syncing is idempotent and keeps report ids stable.
    ids = set(RejectionReport.objects.values_list("external_id", flat=True))
    ds.sync_dataset(ds.load_dataset(REPO_DATASET), include_samples=True)
    assert set(RejectionReport.objects.values_list("external_id", flat=True)) == ids


@pytest.mark.django_db
def test_sync_adopts_local_facility_with_same_slug(tmp_dataset):
    Facility.objects.create(
        slug="pa-example-sci",
        name="Local copy",
        street="x",
        city="Town",
        state="PA",
        postal_code="00001",
    )
    write(tmp_dataset, "facilities/pa/pa-example-sci.json", FACILITY)
    assert ds.sync_dataset(ds.load_dataset(tmp_dataset)).updated == 1
    assert Facility.objects.get(slug="pa-example-sci").origin == Origin.DATASET


# --------------------------------------------------------------- export ---


@pytest.mark.django_db
def test_export_roundtrip_validates(schema, facility):
    data = ds.facility_to_dataset(facility)
    assert data["jurisdiction"] == "test-doc"
    assert data["address"]["street"] == ["1 Prison Road"]
    assert not list(ds.validator_for(schema, "facility").iter_errors(data))
    assert ds.facility_dataset_path(facility) == "facilities/pa/test-sci.json"
    facility.is_sample, facility.active = True, False
    exported = ds.facility_to_dataset(facility)
    assert exported["sample"] is True and exported["active"] is False
    assert ds.facility_dataset_path(facility).startswith("sample/")
    assert ds.dumps({"a": 1}).endswith("\n")


# ------------------------------------------------------------- commands ---


@pytest.mark.django_db
def test_sync_dataset_command(capsys, tmp_dataset):
    call_command("sync_dataset", "--check", "--dataset-dir", str(REPO_DATASET))
    assert "Dataset is valid" in capsys.readouterr().out
    assert not Facility.objects.exists()

    call_command("sync_dataset", "--include-samples", "--dataset-dir", str(REPO_DATASET))
    assert Facility.objects.filter(is_sample=True).exists()

    write(tmp_dataset, "facilities/pa/broken.json", {"id": "x"})
    with pytest.raises(CommandError, match="problem"):
        call_command("sync_dataset", "--dataset-dir", str(tmp_dataset))
    with pytest.raises(CommandError, match="not found"):
        call_command("sync_dataset", "--dataset-dir", str(tmp_dataset / "missing"))
