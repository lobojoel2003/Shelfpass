"""Write this instance's shareable rejection reports as a dataset file."""

import datetime
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from shelfpass.facilities.history import public_reports


class Command(BaseCommand):
    help = (
        "Export anonymised returns (from groups that share data) in the dataset's rejections "
        "format, ready to add to dataset/rejections/ in a pull request."
    )

    def add_arguments(self, parser):
        parser.add_argument("--output", "-o", type=Path, help="File to write (default: stdout).")
        parser.add_argument("--reporter", default="", help="Name to credit in the file.")
        parser.add_argument("--since", help="Only returns received on or after YYYY-MM-DD.")

    def handle(self, *args, output=None, reporter="", since=None, **options):
        start = None
        if since:
            try:
                start = datetime.date.fromisoformat(since)
            except ValueError as exc:
                raise CommandError("--since must be YYYY-MM-DD") from exc
        payload = {
            "reporter": reporter,
            "license": "CC-BY-SA-4.0",
            "generated": timezone.now().isoformat(timespec="seconds"),
            "reports": public_reports(since=start),
        }
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        if output:
            output.write_text(text, encoding="utf-8")
            self.stdout.write(
                self.style.SUCCESS(f"Wrote {len(payload['reports'])} reports to {output}.")
            )
        else:
            self.stdout.write(text, ending="")
