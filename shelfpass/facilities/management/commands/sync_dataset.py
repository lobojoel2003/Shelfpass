"""Validate the open facility-rules dataset and import it into the database."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from shelfpass.facilities.dataset import DatasetError, dataset_root, load_dataset, sync_dataset


class Command(BaseCommand):
    help = (
        "Validate dataset/ against its schema and upsert jurisdictions, facilities and rejections."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dataset-dir", type=Path, default=None, help="Defaults to SHELFPASS_DATASET_DIR."
        )
        parser.add_argument(
            "--include-samples", action="store_true", help="Also import fictional sample records."
        )
        parser.add_argument(
            "--check", action="store_true", help="Only validate; don't touch the database."
        )

    def handle(self, *args, dataset_dir=None, include_samples=False, check=False, **options):
        root = dataset_dir or dataset_root()
        try:
            dataset = load_dataset(root)
        except DatasetError as exc:
            raise CommandError(str(exc)) from exc

        counts = {
            kind: len(dataset.of_kind(kind, include_samples=True))
            for kind in ("jurisdiction", "facility", "rejections")
        }
        self.stdout.write(
            f"Dataset {dataset.version} at {root}: {counts['jurisdiction']} jurisdictions, "
            f"{counts['facility']} facilities, {counts['rejections']} rejection files (including samples)."
        )
        if not dataset.is_valid:
            for error in dataset.errors:
                self.stderr.write(self.style.ERROR(f"  ✗ {error}"))
            raise CommandError(f"{len(dataset.errors)} problem(s) found in the dataset.")
        if check:
            self.stdout.write(self.style.SUCCESS("Dataset is valid."))
            return

        result = sync_dataset(dataset, include_samples=include_samples)
        self.stdout.write(self.style.SUCCESS(f"Synced: {result}."))
