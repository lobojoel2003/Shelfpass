"""Rejection history for a facility, merged from every group and the dataset.

Nothing here ever exposes who a package was for. Free-text return notes are
shown only to the group that wrote them.
"""

from __future__ import annotations

import datetime
from collections import Counter
from dataclasses import dataclass

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from shelfpass.facilities.models import Facility, RejectionReport
from shelfpass.facilities.vocab import (
    RULE_RELATED_REASONS,
    BookCondition,
    BookFormat,
    RejectionReason,
)

REASON_LABELS = dict(RejectionReason.choices)
FORMAT_LABELS = dict(BookFormat.choices)
CONDITION_LABELS = dict(BookCondition.choices)


@dataclass(frozen=True)
class RejectionEvent:
    date: datetime.date
    month_only: bool
    reason: str
    title: str = ""
    authors: str = ""
    isbn: str = ""
    format: str = ""
    condition: str = ""
    detail: str = ""
    source: str = ""
    facility_slug: str = ""
    facility_name: str = ""

    @property
    def reason_label(self) -> str:
        return REASON_LABELS.get(self.reason, self.reason)

    @property
    def format_label(self) -> str:
        parts = [CONDITION_LABELS.get(self.condition, ""), FORMAT_LABELS.get(self.format, "")]
        return " ".join(p for p in parts if p).lower()


@dataclass(frozen=True)
class ReasonCount:
    code: str
    label: str
    count: int
    percent: int


def window_start(days: int | None = None) -> datetime.date:
    days = days if days is not None else settings.SHELFPASS["REJECTION_WINDOW_DAYS"]
    return timezone.localdate() - datetime.timedelta(days=days)


def _local_returns(facilities=None, since=None):
    from shelfpass.shipping.models import Return

    returns = Return.objects.select_related(
        "flagged_item", "organization", "facility", "package"
    ).prefetch_related("package__items")
    if facilities is not None:
        returns = returns.filter(facility__in=facilities)
    if since:
        returns = returns.filter(received_on__gte=since)
    return returns


def rejection_events(
    facility: Facility | None = None,
    since: datetime.date | None = None,
    viewer_org=None,
    limit: int | None = None,
) -> list[RejectionEvent]:
    """Newest-first events for one facility (or all, when ``facility`` is None)."""
    facilities = [facility] if facility is not None else None
    events: list[RejectionEvent] = []
    for ret in _local_returns(facilities, since):
        item = ret.flagged_item
        if item is None:
            package_items = list(ret.package.items.all())
            item = package_items[0] if len(package_items) == 1 else None
        own = viewer_org is not None and ret.organization_id == viewer_org.pk
        events.append(
            RejectionEvent(
                date=ret.received_on,
                month_only=False,
                reason=ret.reason,
                title=item.title if item else "",
                authors=item.authors if item else "",
                isbn=item.isbn if item else "",
                format=item.format if item else "",
                condition=item.condition if item else "",
                detail=ret.detail if own else "",
                source="Your group" if own else "Another group on this site",
                facility_slug=ret.facility.slug,
                facility_name=ret.facility.name,
            )
        )
    reports = RejectionReport.objects.select_related("facility")
    if facility is not None:
        reports = reports.filter(facility=facility)
    if since:
        reports = reports.filter(month__gte=since.replace(day=1))
    for report in reports:
        events.append(
            RejectionEvent(
                date=report.month,
                month_only=True,
                reason=report.reason,
                title=report.title,
                authors=report.authors,
                isbn=report.isbn,
                format=report.format,
                condition=report.condition,
                detail=report.detail,
                source=report.reporter or "Shared dataset",
                facility_slug=report.facility.slug,
                facility_name=report.facility.name,
            )
        )
    events.sort(key=lambda e: (e.date, e.month_only is False), reverse=True)
    return events[:limit] if limit else events


def reason_breakdown(events: list[RejectionEvent]) -> list[ReasonCount]:
    counts = Counter(e.reason for e in events)
    total = sum(counts.values()) or 1
    return [
        ReasonCount(code, REASON_LABELS.get(code, code), n, round(100 * n / total))
        for code, n in counts.most_common()
    ]


def shipping_stats(facility: Facility, since: datetime.date | None = None) -> dict[str, int]:
    """Packages shipped to a facility from this instance and how many bounced."""
    from shelfpass.shipping.models import Package

    packages = Package.objects.filter(facility=facility).exclude(status=Package.Status.PACKING)
    if since:
        packages = packages.filter(shipped_on__gte=since)
    stats = packages.aggregate(
        shipped=Count("pk"),
        returned=Count(
            "pk",
            filter=Q(return_record__reason__in=[str(r) for r in RULE_RELATED_REASONS]),
        ),
    )
    shipped = stats["shipped"] or 0
    returned = stats["returned"] or 0
    return {
        "shipped": shipped,
        "returned": returned,
        "rate": round(100 * returned / shipped) if shipped else 0,
    }


def public_reports(since: datetime.date | None = None) -> list[dict]:
    """Anonymised local returns, in the dataset's ``rejections`` report format.

    Only groups that opted in (``share_rejections``) are included, and only
    for facilities that exist in the shared dataset.
    """
    returns = _local_returns(since=since).filter(
        organization__share_rejections=True, facility__origin="dataset", facility__is_sample=False
    )
    reports = []
    for ret in returns.order_by("received_on", "pk"):
        item = ret.flagged_item
        report = {
            "facility": ret.facility.slug,
            "month": ret.received_on.strftime("%Y-%m"),
            "reason": ret.reason,
        }
        if item is not None:
            book = {
                "title": item.title,
                "authors": item.authors,
                "isbn": item.isbn,
                "format": item.format,
                "condition": item.condition,
            }
            report["book"] = {k: v for k, v in book.items() if v}
        reports.append(report)
    return reports
