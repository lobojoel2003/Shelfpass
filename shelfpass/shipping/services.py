"""Package lifecycle: packing, shipping, delivery and returns.

All state changes go through these functions so stock counts, requested-item
status and request status stay consistent.
"""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from shelfpass.correspondence.models import BookRequest, RequestedItem
from shelfpass.facilities.vocab import BookCondition, ItemSource, RejectionReason
from shelfpass.inventory.models import Book
from shelfpass.shipping.models import Package, PackageItem, Return


def current_package(book_request: BookRequest) -> Package | None:
    return book_request.packages.filter(status=Package.Status.PACKING).order_by("-pk").first()


@transaction.atomic
def start_package(book_request: BookRequest, user=None, force_new: bool = False) -> Package:
    """Return the request's open package, creating one if needed (or if ``force_new``)."""
    if book_request.is_closed:
        raise ValidationError("Reopen the request before packing books for it.")
    existing = None if force_new else current_package(book_request)
    if existing:
        return existing
    person = book_request.person
    package = Package.objects.create(
        organization=book_request.organization,
        request=book_request,
        person=person,
        facility=person.facility or book_request.facility,
        created_by=user,
    )
    book_request.refresh_status()
    return package


def _require_editable(package: Package) -> None:
    if not package.is_editable:
        raise ValidationError(f"{package.reference} has already shipped and can't be changed.")


def _sync_requested_item(item: RequestedItem | None) -> None:
    if item is None:
        return
    live = item.package_items.exclude(
        package__status__in=[Package.Status.RETURNED, Package.Status.LOST]
    ).exists()
    if live and item.status != RequestedItem.Status.PACKED:
        item.status = RequestedItem.Status.PACKED
        item.save(update_fields=["status"])
    elif not live and item.status == RequestedItem.Status.PACKED:
        item.status = RequestedItem.Status.OPEN
        item.save(update_fields=["status"])


@transaction.atomic
def add_book(
    package: Package, book: Book, requested_item: RequestedItem | None = None
) -> PackageItem:
    _require_editable(package)
    if book.organization_id != package.organization_id:
        raise ValidationError("That book belongs to another group's shelf.")
    if requested_item is not None and requested_item.request_id != package.request_id:
        raise ValidationError("That requested item belongs to a different letter.")
    locked = Book.objects.select_for_update().get(pk=book.pk)
    if locked.quantity < 1:
        raise ValidationError(f"“{book.title}” is out of stock.")
    locked.quantity = F("quantity") - 1
    locked.save(update_fields=["quantity", "updated_at"])
    item = PackageItem.from_book(package, book, requested_item)
    item.save()
    _sync_requested_item(requested_item)
    return item


@transaction.atomic
def add_vendor_item(
    package: Package,
    title: str,
    authors: str = "",
    isbn: str = "",
    format: str = "paperback",
    requested_item: RequestedItem | None = None,
) -> PackageItem:
    """A new book ordered from a vendor and shipped straight to the facility."""
    _require_editable(package)
    item = PackageItem.objects.create(
        package=package,
        requested_item=requested_item,
        title=title.strip(),
        authors=authors.strip(),
        isbn=isbn,
        format=format,
        condition=BookCondition.NEW,
        source=ItemSource.VENDOR,
    )
    _sync_requested_item(requested_item)
    return item


@transaction.atomic
def remove_item(item: PackageItem) -> None:
    _require_editable(item.package)
    if item.book_id:
        Book.objects.filter(pk=item.book_id).update(quantity=F("quantity") + 1)
    requested = item.requested_item
    item.delete()
    _sync_requested_item(requested)


@transaction.atomic
def discard_package(package: Package) -> None:
    """Delete an empty-or-not packing package, putting its books back on the shelf."""
    _require_editable(package)
    book_request = package.request
    for item in list(package.items.all()):
        remove_item(item)
    package.delete()
    book_request.refresh_status()


@transaction.atomic
def ship(
    package: Package,
    shipped_on: datetime.date,
    carrier: str = "",
    tracking_number: str = "",
    weight_oz: int | None = None,
    postage_cents: int | None = None,
    override_note: str = "",
) -> Package:
    _require_editable(package)
    if not package.items.exists():
        raise ValidationError("Add at least one book before shipping.")
    package.weight_oz = weight_oz or package.weight_oz
    blocking = [issue for issue in package.check_rules() if issue.is_blocking]
    if blocking and not override_note.strip():
        raise ValidationError(
            "This package breaks the facility's rules. Fix the problems or explain why "
            "it should ship anyway."
        )
    package.status = Package.Status.SHIPPED
    package.shipped_on = shipped_on
    package.carrier = carrier
    package.tracking_number = tracking_number.strip()
    package.postage_cents = postage_cents
    package.override_note = override_note.strip()[:300]
    package.save()
    package.request.refresh_status()
    return package


@transaction.atomic
def mark_delivered(package: Package, delivered_on: datetime.date) -> Package:
    if package.status != Package.Status.SHIPPED:
        raise ValidationError("Only shipped packages can be marked delivered.")
    package.status = Package.Status.DELIVERED
    package.delivered_on = delivered_on
    package.save(update_fields=["status", "delivered_on", "updated_at"])
    package.request.refresh_status()
    return package


@transaction.atomic
def log_return(
    package: Package,
    reason: str,
    received_on: datetime.date,
    detail: str = "",
    flagged_item: PackageItem | None = None,
    restock: bool = True,
    user=None,
) -> Return:
    """Record that a package bounced (or vanished) and why."""
    if package.status not in (Package.Status.SHIPPED, Package.Status.DELIVERED):
        raise ValidationError("Only packages that were shipped can be logged as returned.")
    if flagged_item is not None and flagged_item.package_id != package.pk:
        raise ValidationError("The flagged book isn't in this package.")
    lost = reason == RejectionReason.NO_RESPONSE
    restock = restock and not lost
    record = Return.objects.create(
        package=package,
        organization=package.organization,
        facility=package.facility,
        received_on=received_on,
        reason=reason,
        detail=detail.strip(),
        flagged_item=flagged_item,
        restocked=restock,
        logged_by=user,
    )
    package.status = Package.Status.LOST if lost else Package.Status.RETURNED
    package.save(update_fields=["status", "updated_at"])
    for item in package.items.select_related("requested_item"):
        if restock and item.book_id:
            Book.objects.filter(pk=item.book_id).update(quantity=F("quantity") + 1)
        _sync_requested_item(item.requested_item)
    package.request.refresh_status()
    return record
