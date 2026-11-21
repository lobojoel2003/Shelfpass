"""What has already been sent to a person (for "already sent" warnings)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from shelfpass.core.text import normalize_isbn, similarity

DUPLICATE_THRESHOLD = 0.88


@dataclass(frozen=True)
class SentBook:
    title: str
    authors: str
    isbn: str
    shipped_on: datetime.date | None
    package_id: int
    package_reference: str
    package_status: str

    def matches(self, title: str, isbn: str = "") -> bool:
        a, b = normalize_isbn(self.isbn), normalize_isbn(isbn)
        if a and b and a == b:
            return True
        return similarity(self.title, title) >= DUPLICATE_THRESHOLD


def sent_books(person, exclude_package_id: int | None = None) -> list[SentBook]:
    """Books in packages that left the building (or are being packed) for this person.

    Returned and vanished packages are excluded: the person never got those.
    """
    from shelfpass.shipping.models import Package, PackageItem

    items = (
        PackageItem.objects.filter(package__person=person)
        .exclude(package__status__in=[Package.Status.RETURNED, Package.Status.LOST])
        .select_related("package")
        .order_by("-package__shipped_on", "-package__created_at")
    )
    if exclude_package_id:
        items = items.exclude(package_id=exclude_package_id)
    return [
        SentBook(
            title=item.title,
            authors=item.authors,
            isbn=item.isbn,
            shipped_on=item.package.shipped_on,
            package_id=item.package_id,
            package_reference=item.package.reference,
            package_status=item.package.get_status_display(),
        )
        for item in items
    ]


def find_previous(history: list[SentBook], title: str, isbn: str = "") -> SentBook | None:
    return next((sent for sent in history if sent.matches(title, isbn)), None)
