"""Controlled vocabularies shared by the app and the open dataset.

These codes appear in dataset files (``dataset/schema/dataset.schema.json``)
and in exported rejection reports, so treat them as a public API: add new
codes freely, but never rename or remove one. ``tests/test_dataset.py``
checks that the schema and this module stay in sync.
"""

from __future__ import annotations

from django.db import models


class RejectionReason(models.TextChoices):
    REFUSED_NO_REASON = "refused-no-reason", "Refused (no reason given)"
    UNAUTHORIZED_SENDER = "unauthorized-sender", "Unauthorized sender / not an approved vendor"
    HARDCOVER = "hardcover", "Hardcover not allowed"
    USED_BOOK = "used-book", "Used books not allowed"
    NO_INVOICE = "no-invoice", "Missing invoice or receipt"
    CONTENT = "content", "Content banned or censored"
    TOO_MANY = "too-many-items", "Too many books or over the weight limit"
    MARKINGS = "markings", "Writing, stickers or damage in a book"
    PACKAGING = "packaging", "Packaging or label problem"
    RECIPIENT_MOVED = "recipient-moved", "Recipient transferred or released"
    RECIPIENT_UNKNOWN = "recipient-unknown", "Recipient not found or wrong ID"
    NO_RESPONSE = "no-response", "Never arrived (vanished)"
    OTHER = "other", "Other"


#: Reasons that say something about the facility's rules (as opposed to the
#: recipient moving away). Used for the "rejection rate" on facility pages.
RULE_RELATED_REASONS = frozenset(
    {
        RejectionReason.REFUSED_NO_REASON,
        RejectionReason.UNAUTHORIZED_SENDER,
        RejectionReason.HARDCOVER,
        RejectionReason.USED_BOOK,
        RejectionReason.NO_INVOICE,
        RejectionReason.CONTENT,
        RejectionReason.TOO_MANY,
        RejectionReason.MARKINGS,
        RejectionReason.PACKAGING,
        RejectionReason.NO_RESPONSE,
    }
)


class ContentCategory(models.TextChoices):
    SEXUALLY_EXPLICIT = "sexually-explicit", "Sexually explicit material or nudity"
    WEAPONS = "weapons-violence", "Weapons, explosives or instructions for violence"
    DRUGS = "drug-manufacture", "Drug or alcohol manufacture"
    ESCAPE = "escape-security", "Escape, lock-picking or security"
    GANG = "gang-related", "Gang-related material"
    HATE = "hate", "Racial, ethnic or religious hatred"
    MAPS = "maps-travel", "Maps, atlases and travel guides"
    MARTIAL_ARTS = "martial-arts", "Martial arts and combat training"
    TATTOO = "tattoo", "Tattooing"
    RPG = "role-playing-games", "Role-playing games"
    TECHNOLOGY = "technology", "Computer programming, hacking or electronics"
    TRUE_CRIME = "true-crime", "True crime"
    OTHER = "other", "Other restricted content"


#: Subject keywords (from Open Library or volunteers) that suggest a content
#: category. Kept deliberately narrow: these produce warnings, not blocks.
CONTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    ContentCategory.MAPS: ("maps", "atlases", "atlas", "road maps", "travel guide", "guidebooks"),
    ContentCategory.MARTIAL_ARTS: (
        "martial arts",
        "karate",
        "kung fu",
        "self-defense",
        "jiu-jitsu",
    ),
    ContentCategory.TATTOO: ("tattoo", "tattooing"),
    ContentCategory.RPG: (
        "role playing",
        "role-playing",
        "dungeons & dragons",
        "dungeons and dragons",
    ),
    ContentCategory.TECHNOLOGY: (
        "computer programming",
        "hacking",
        "computer security",
        "electronics",
    ),
    ContentCategory.WEAPONS: ("firearms", "explosives", "weapons", "gunsmithing"),
    ContentCategory.ESCAPE: ("lock picking", "lockpicking", "escapes"),
    ContentCategory.TRUE_CRIME: ("true crime",),
    ContentCategory.SEXUALLY_EXPLICIT: ("erotica", "erotic literature"),
}


def guess_content_flags(*texts: str) -> list[str]:
    """Content categories suggested by subjects/titles, in vocabulary order."""
    haystack = " | ".join(t.lower() for t in texts if t)
    found = [code for code, words in CONTENT_KEYWORDS.items() if any(w in haystack for w in words)]
    return [c.value for c in ContentCategory if c.value in found]


class FacilityKind(models.TextChoices):
    STATE_PRISON = "state-prison", "State prison"
    FEDERAL_PRISON = "federal-prison", "Federal prison"
    COUNTY_JAIL = "county-jail", "County or city jail"
    IMMIGRATION = "immigration-detention", "Immigration detention"
    JUVENILE = "juvenile", "Juvenile facility"
    PRIVATE = "private-prison", "Privately operated prison"
    OTHER = "other", "Other"


class JurisdictionKind(models.TextChoices):
    FEDERAL = "federal", "Federal"
    STATE = "state", "State department of corrections"
    COUNTY = "county", "County or city"
    OTHER = "other", "Other"


US_STATES: list[tuple[str, str]] = [
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"),
    ("CA", "California"), ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"),
    ("DC", "District of Columbia"), ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"),
    ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"), ("KS", "Kansas"),
    ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
    ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"), ("MS", "Mississippi"),
    ("MO", "Missouri"), ("MT", "Montana"), ("NE", "Nebraska"), ("NV", "Nevada"),
    ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NM", "New Mexico"), ("NY", "New York"),
    ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"), ("OK", "Oklahoma"),
    ("OR", "Oregon"), ("PA", "Pennsylvania"), ("PR", "Puerto Rico"), ("RI", "Rhode Island"),
    ("SC", "South Carolina"), ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"),
    ("UT", "Utah"), ("VT", "Vermont"), ("VA", "Virginia"), ("WA", "Washington"),
    ("WV", "West Virginia"), ("WI", "Wisconsin"), ("WY", "Wyoming"),
]  # fmt: skip


class BookFormat(models.TextChoices):
    PAPERBACK = "paperback", "Paperback"
    MASS_MARKET = "mass-market", "Mass-market paperback"
    HARDCOVER = "hardcover", "Hardcover"
    SPIRAL = "spiral", "Spiral-bound"
    OTHER = "other", "Other"


SOFTCOVER_FORMATS = frozenset({BookFormat.PAPERBACK, BookFormat.MASS_MARKET})


class BookCondition(models.TextChoices):
    NEW = "new", "New"
    USED = "used", "Used"


class ItemSource(models.TextChoices):
    SHELF = "shelf", "From our shelf"
    VENDOR = "vendor", "Shipped new from a vendor"
