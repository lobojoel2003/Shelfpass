"""Packages sent to people, the books in them, and returns (rejections)."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from shelfpass.correspondence.models import BookRequest, Person, RequestedItem
from shelfpass.facilities.models import Facility
from shelfpass.facilities.vocab import BookCondition, BookFormat, ItemSource, RejectionReason
from shelfpass.inventory.models import Book
from shelfpass.orgs.models import Organization


class Package(models.Model):
    class Status(models.TextChoices):
        PACKING = "packing", "Packing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        RETURNED = "returned", "Returned"
        LOST = "lost", "Vanished"

    class Carrier(models.TextChoices):
        MEDIA_MAIL = "usps-media", "USPS Media Mail"
        USPS_GROUND = "usps-ground", "USPS Ground Advantage"
        USPS_PRIORITY = "usps-priority", "USPS Priority Mail"
        UPS = "ups", "UPS"
        FEDEX = "fedex", "FedEx"
        VENDOR = "vendor", "Shipped by vendor"
        OTHER = "other", "Other"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="packages"
    )
    request = models.ForeignKey(BookRequest, on_delete=models.CASCADE, related_name="packages")
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="packages")
    facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name="packages")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PACKING)
    shipped_on = models.DateField(null=True, blank=True)
    delivered_on = models.DateField(null=True, blank=True)
    carrier = models.CharField(max_length=20, choices=Carrier.choices, blank=True)
    tracking_number = models.CharField(max_length=60, blank=True)
    weight_oz = models.PositiveIntegerField("weight (oz)", null=True, blank=True)
    postage_cents = models.PositiveIntegerField(null=True, blank=True)
    override_note = models.CharField(
        max_length=300,
        blank=True,
        help_text="Why this package shipped despite a rule warning.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["facility", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference} to {self.person.name}"

    def get_absolute_url(self) -> str:
        return reverse("shipping:detail", args=[self.pk])

    @property
    def reference(self) -> str:
        return f"P-{self.pk:05d}" if self.pk else "P-new"

    @property
    def is_editable(self) -> bool:
        return self.status == self.Status.PACKING

    @property
    def postage_display(self) -> str:
        return f"${self.postage_cents / 100:,.2f}" if self.postage_cents is not None else ""

    def estimated_weight_oz(self) -> int | None:
        if self.weight_oz:
            return self.weight_oz
        weights = [
            item.book.weight_oz for item in self.items.all() if item.book and item.book.weight_oz
        ]
        return sum(weights) if weights else None

    def check_rules(self):
        items = list(self.items.all())
        return self.facility.ruleset.check_items(items, self.estimated_weight_oz())


class PackageItem(models.Model):
    """A book in a package. Details are copied so history survives shelf edits."""

    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="items")
    book = models.ForeignKey(
        Book, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    requested_item = models.ForeignKey(
        RequestedItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="package_items",
    )
    title = models.CharField(max_length=300)
    authors = models.CharField(max_length=300, blank=True)
    isbn = models.CharField(max_length=13, blank=True)
    format = models.CharField(
        max_length=20, choices=BookFormat.choices, default=BookFormat.PAPERBACK
    )
    condition = models.CharField(
        max_length=10, choices=BookCondition.choices, default=BookCondition.USED
    )
    content_flags = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=10, choices=ItemSource.choices, default=ItemSource.SHELF)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["pk"]

    def __str__(self) -> str:
        return self.title

    @classmethod
    def from_book(cls, package: Package, book: Book, requested_item: RequestedItem | None = None):
        return cls(
            package=package,
            book=book,
            requested_item=requested_item,
            title=book.title,
            authors=book.authors,
            isbn=book.isbn,
            format=book.format,
            condition=book.condition,
            content_flags=list(book.content_flags),
            source=ItemSource.SHELF,
        )


class Return(models.Model):
    """A package that came back (or never arrived), with the reason given."""

    package = models.OneToOneField(Package, on_delete=models.CASCADE, related_name="return_record")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="returns")
    facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name="returns")
    received_on = models.DateField(default=timezone.localdate)
    reason = models.CharField(max_length=30, choices=RejectionReason.choices)
    detail = models.TextField(
        blank=True, help_text="Copy what the slip or stamp said, word for word if you can."
    )
    flagged_item = models.ForeignKey(
        PackageItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The book the facility objected to, if they said.",
    )
    restocked = models.BooleanField(default=False)
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_on", "-pk"]
        indexes = [models.Index(fields=["facility", "received_on"])]

    def __str__(self) -> str:
        return f"Return of {self.package.reference}: {self.get_reason_display()}"

    @property
    def is_lost(self) -> bool:
        return self.reason == RejectionReason.NO_RESPONSE
