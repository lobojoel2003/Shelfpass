"""Facilities, the jurisdictions that set their rules, and public rejection reports."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.functional import cached_property

from shelfpass.facilities.rules import RuleSet
from shelfpass.facilities.vocab import (
    US_STATES,
    BookCondition,
    BookFormat,
    FacilityKind,
    JurisdictionKind,
    RejectionReason,
)


class Origin(models.TextChoices):
    DATASET = "dataset", "Shared dataset"
    LOCAL = "local", "Added on this instance"


class SourcedRecord(models.Model):
    """Fields shared by jurisdictions and facilities that come from the dataset."""

    rules = models.JSONField(default=dict, blank=True)
    sources = models.JSONField(
        default=list,
        blank=True,
        help_text="Where the rules come from: list of {title, url, accessed}.",
    )
    last_verified = models.DateField(null=True, blank=True)
    origin = models.CharField(max_length=10, choices=Origin.choices, default=Origin.LOCAL)
    is_sample = models.BooleanField(
        default=False, help_text="Fictional demo record from dataset/sample."
    )
    dataset_path = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @property
    def is_from_dataset(self) -> bool:
        return self.origin == Origin.DATASET


class Jurisdiction(SourcedRecord):
    """A rule-setting authority: the federal BOP, a state DOC, a county sheriff."""

    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=JurisdictionKind.choices)
    state = models.CharField(max_length=2, choices=US_STATES, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @cached_property
    def ruleset(self) -> RuleSet:
        return RuleSet.from_layers(self.rules)


class FacilityQuerySet(models.QuerySet):
    def active(self):
        return self.filter(active=True)

    def search(self, query: str):
        query = (query or "").strip()
        if not query:
            return self
        return self.filter(
            models.Q(name__icontains=query)
            | models.Q(city__icontains=query)
            | models.Q(state__iexact=query)
            | models.Q(slug__icontains=query)
        )


class Facility(SourcedRecord):
    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=200)
    kind = models.CharField(
        max_length=30, choices=FacilityKind.choices, default=FacilityKind.STATE_PRISON
    )
    jurisdiction = models.ForeignKey(
        Jurisdiction, null=True, blank=True, on_delete=models.SET_NULL, related_name="facilities"
    )
    street = models.TextField(help_text="Street address or PO box, one line per row.")
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, choices=US_STATES)
    postal_code = models.CharField(max_length=12)
    phone = models.CharField(max_length=40, blank=True)
    website = models.URLField(blank=True)
    notes = models.TextField(blank=True, help_text="Anything volunteers should know.")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = FacilityQuerySet.as_manager()

    class Meta:
        ordering = ["state", "name"]
        verbose_name_plural = "facilities"

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state})"

    def get_absolute_url(self) -> str:
        return reverse("facilities:detail", args=[self.slug])

    @cached_property
    def ruleset(self) -> RuleSet:
        layers = [self.jurisdiction.rules] if self.jurisdiction_id else []
        return RuleSet.from_layers(*layers, self.rules)

    @property
    def address_lines(self) -> list[str]:
        lines = [line.strip() for line in self.street.splitlines() if line.strip()]
        return [*lines, f"{self.city}, {self.state} {self.postal_code}".strip()]

    @property
    def book_address_lines(self) -> list[str]:
        """Address book packages go to: a central processing centre when one is set."""
        central = list(self.ruleset.book_mail_address)
        return central or [self.name, *self.address_lines]

    @property
    def all_sources(self) -> list[dict]:
        own = list(self.sources or [])
        inherited = list(self.jurisdiction.sources or []) if self.jurisdiction_id else []
        return own + [s for s in inherited if s not in own]


class RejectionReport(models.Model):
    """An anonymised rejection imported from the shared dataset.

    Returns logged on this instance live in :class:`shelfpass.shipping.models.Return`;
    these are the ones other instances contributed via ``dataset/rejections``.
    """

    external_id = models.CharField(max_length=64, unique=True)
    facility = models.ForeignKey(
        Facility, on_delete=models.CASCADE, related_name="rejection_reports"
    )
    month = models.DateField(help_text="First day of the month the package came back.")
    reason = models.CharField(max_length=30, choices=RejectionReason.choices)
    title = models.CharField(max_length=300, blank=True)
    authors = models.CharField(max_length=300, blank=True)
    isbn = models.CharField(max_length=13, blank=True)
    format = models.CharField(max_length=20, choices=BookFormat.choices, blank=True)
    condition = models.CharField(max_length=10, choices=BookCondition.choices, blank=True)
    detail = models.CharField(max_length=500, blank=True)
    reporter = models.CharField(max_length=200, blank=True)
    dataset_path = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-month", "facility__name"]

    def __str__(self) -> str:
        return f"{self.facility} {self.month:%Y-%m} {self.reason}"
