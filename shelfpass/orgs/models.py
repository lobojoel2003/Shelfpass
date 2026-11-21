"""Groups (books-to-prisoners organisations) and their volunteers.

Every piece of group-owned data (people, letters, shelf, packages) carries a
foreign key to :class:`Organization`. Facilities and their rules are shared by
every group on an instance.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Organization(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    return_address = models.TextField(
        help_text="Printed as the sender on labels and packing slips. One line per row.",
    )
    contact_email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    packing_slip_note = models.TextField(
        blank=True,
        default=(
            "These books are a free gift from a volunteer books-to-prisoners program. "
            "No payment is due."
        ),
        help_text="Printed at the bottom of every packing slip.",
    )
    share_rejections = models.BooleanField(
        default=True,
        help_text=(
            "Include this group's anonymised return reports in the public rejection "
            "dataset. Names and ID numbers are never shared."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "group"
        verbose_name_plural = "groups"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:80] or "group"
        super().save(*args, **kwargs)

    @property
    def return_address_lines(self) -> list[str]:
        return [line.strip() for line in self.return_address.splitlines() if line.strip()]

    @property
    def sender_lines(self) -> list[str]:
        """Return address for labels, starting with the group's name exactly once."""
        lines = self.return_address_lines
        if lines and lines[0].casefold() == self.name.casefold():
            return lines
        return [self.name, *lines]


class Membership(models.Model):
    class Role(models.TextChoices):
        COORDINATOR = "coordinator", "Coordinator"
        VOLUNTEER = "volunteer", "Volunteer"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VOLUNTEER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["organization__name", "user__username"]
        constraints = [
            models.UniqueConstraint(fields=["user", "organization"], name="unique_membership"),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.organization} ({self.get_role_display()})"

    @property
    def is_coordinator(self) -> bool:
        return self.role == self.Role.COORDINATOR
