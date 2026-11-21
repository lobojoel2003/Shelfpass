"""People who write to the group, and the book requests in their letters."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from shelfpass.core.text import normalize_inmate_id
from shelfpass.facilities.models import Facility
from shelfpass.orgs.models import Organization


class Person(models.Model):
    """An incarcerated reader. Never exposed outside the owning group."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="people")
    name = models.CharField(max_length=200)
    inmate_id = models.CharField("ID number", max_length=40)
    inmate_id_normalized = models.CharField(max_length=40, editable=False, db_index=True)
    facility = models.ForeignKey(
        Facility, null=True, blank=True, on_delete=models.SET_NULL, related_name="people"
    )
    housing = models.CharField(
        max_length=80, blank=True, help_text="Unit, block or cell, if the facility needs it."
    )
    active = models.BooleanField(
        default=True, help_text="Untick when someone is released or asks to stop."
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "people"
        indexes = [models.Index(fields=["organization", "inmate_id_normalized"])]

    def __str__(self) -> str:
        return f"{self.name} #{self.inmate_id}"

    def save(self, *args, **kwargs):
        self.inmate_id = self.inmate_id.strip()
        self.inmate_id_normalized = normalize_inmate_id(self.inmate_id)
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("correspondence:person_detail", args=[self.pk])


class BookRequest(models.Model):
    """One letter asking for books."""

    class Status(models.TextChoices):
        OPEN = "open", "Waiting"
        PACKING = "packing", "Packing"
        SHIPPED = "shipped", "Shipped"
        RETURNED = "returned", "Returned"
        CLOSED = "closed", "Closed"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="book_requests"
    )
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="requests")
    facility = models.ForeignKey(
        Facility,
        on_delete=models.PROTECT,
        related_name="book_requests",
        help_text="Where the person was when they wrote.",
    )
    received_on = models.DateField(default=timezone.localdate)
    letter_notes = models.TextField(
        "notes from the letter",
        blank=True,
        help_text="Anything else they said: interests, reading level.",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-received_on", "-pk"]
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self) -> str:
        return f"{self.reference} from {self.person.name}"

    def get_absolute_url(self) -> str:
        return reverse("correspondence:request_detail", args=[self.pk])

    @property
    def reference(self) -> str:
        return f"R-{self.pk:05d}" if self.pk else "R-new"

    @property
    def is_closed(self) -> bool:
        return self.status == self.Status.CLOSED

    def refresh_status(self, save: bool = True) -> str:
        """Derive the status from the request's packages (unless closed by hand)."""
        from shelfpass.shipping.models import Package

        if self.closed_at:
            status = self.Status.CLOSED
        else:
            packages = list(self.packages.order_by("created_at", "pk"))
            if not packages:
                status = self.Status.OPEN
            elif any(p.status == Package.Status.PACKING for p in packages):
                status = self.Status.PACKING
            elif packages[-1].status in (Package.Status.RETURNED, Package.Status.LOST):
                status = self.Status.RETURNED
            else:
                status = self.Status.SHIPPED
        if status != self.status:
            self.status = status
            if save:
                self.save(update_fields=["status", "updated_at"])
        return status

    def close(self, reason: str = "") -> None:
        self.closed_at = timezone.now()
        self.close_reason = reason[:200]
        self.status = self.Status.CLOSED
        self.save(update_fields=["closed_at", "close_reason", "status", "updated_at"])

    def reopen(self) -> None:
        self.closed_at = None
        self.close_reason = ""
        self.save(update_fields=["closed_at", "close_reason", "updated_at"])
        self.refresh_status()


class RequestedItem(models.Model):
    """One thing asked for: a specific title ("The Hobbit") or a topic ("GED guide")."""

    class Kind(models.TextChoices):
        TITLE = "title", "Specific title"
        TOPIC = "topic", "Topic or genre"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PACKED = "packed", "Packed"
        UNAVAILABLE = "unavailable", "Couldn't fill"

    request = models.ForeignKey(BookRequest, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=300)
    author = models.CharField(max_length=200, blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.TITLE)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self) -> str:
        return self.description

    @property
    def query_text(self) -> str:
        return f"{self.description} {self.author}".strip()
