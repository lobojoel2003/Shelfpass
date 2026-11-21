"""The group's shelf: books on hand, waiting to be matched to requests."""

from __future__ import annotations

from django.db import models
from django.urls import reverse

from shelfpass.core.text import normalize_isbn
from shelfpass.facilities.vocab import (
    SOFTCOVER_FORMATS,
    BookCondition,
    BookFormat,
    ContentCategory,
    ItemSource,
)
from shelfpass.orgs.models import Organization


class Category(models.TextChoices):
    REFERENCE = "reference", "Dictionaries & reference"
    EDUCATION = "education", "GED & education"
    LANGUAGE = "language", "Language learning"
    LEGAL = "legal", "Law & legal self-help"
    FICTION = "fiction", "General fiction"
    FANTASY = "fantasy", "Fantasy & science fiction"
    MYSTERY = "mystery", "Mystery & thriller"
    ROMANCE = "romance", "Romance"
    HISTORY = "history", "History & politics"
    BIOGRAPHY = "biography", "Biography & memoir"
    SELF_HELP = "self-help", "Self-help & recovery"
    RELIGION = "religion", "Religion & spirituality"
    HEALTH = "health", "Health & fitness"
    BUSINESS = "business", "Business & jobs"
    SCIENCE = "science", "Science & math"
    ARTS = "arts", "Art, drawing & music"
    POETRY = "poetry", "Poetry & plays"
    OTHER = "other", "Other"


#: Words in a free-text request that point at a category ("a GED guide").
CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    Category.REFERENCE: ("dictionary", "thesaurus", "almanac", "encyclopedia", "reference"),
    Category.EDUCATION: ("ged", "hiset", "tasc", "math", "algebra", "grammar", "study", "textbook"),
    Category.LANGUAGE: ("spanish", "english", "french", "language", "esl", "bilingual"),
    Category.LEGAL: ("law", "legal", "habeas", "appeal", "paralegal", "rights"),
    Category.FANTASY: ("fantasy", "sci", "scifi", "science fiction", "dragons", "magic", "wizard"),
    Category.MYSTERY: ("mystery", "thriller", "detective", "crime novel", "suspense"),
    Category.ROMANCE: ("romance", "love story"),
    Category.HISTORY: ("history", "historical", "politics", "civil rights"),
    Category.BIOGRAPHY: ("biography", "memoir", "autobiography"),
    Category.SELF_HELP: ("self help", "recovery", "meditation", "addiction", "anger"),
    Category.RELIGION: ("bible", "quran", "koran", "religion", "spiritual", "buddhism", "torah"),
    Category.HEALTH: ("fitness", "exercise", "yoga", "health", "nutrition", "workout"),
    Category.BUSINESS: ("business", "entrepreneur", "resume", "job", "career", "finance"),
    Category.SCIENCE: ("science", "physics", "biology", "chemistry", "astronomy"),
    Category.ARTS: ("drawing", "art", "music", "guitar", "sketch", "painting"),
    Category.POETRY: ("poetry", "poems", "plays", "shakespeare"),
    Category.FICTION: ("novel", "fiction", "urban fiction", "classics", "westerns"),
}


class BookQuerySet(models.QuerySet):
    def in_stock(self):
        return self.filter(quantity__gt=0)


class Book(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="books")
    title = models.CharField(max_length=300)
    authors = models.CharField(max_length=300, blank=True, help_text="Separate several with ';'.")
    isbn = models.CharField("ISBN-13", max_length=13, blank=True, db_index=True)
    publisher = models.CharField(max_length=200, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    format = models.CharField(
        max_length=20, choices=BookFormat.choices, default=BookFormat.PAPERBACK
    )
    condition = models.CharField(
        max_length=10, choices=BookCondition.choices, default=BookCondition.USED
    )
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    subjects = models.JSONField(default=list, blank=True)
    content_flags = models.JSONField(
        default=list,
        blank=True,
        help_text="Content some facilities restrict (maps, martial arts, …).",
    )
    quantity = models.PositiveIntegerField(default=1)
    location = models.CharField(max_length=60, blank=True, help_text="Shelf or box label.")
    weight_oz = models.PositiveSmallIntegerField("weight (oz)", null=True, blank=True)
    openlibrary_key = models.CharField(max_length=60, blank=True)
    cover_id = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BookQuerySet.as_manager()

    class Meta:
        ordering = ["title", "authors"]
        indexes = [models.Index(fields=["organization", "category"])]

    def __str__(self) -> str:
        return f"{self.title} — {self.authors}" if self.authors else self.title

    def save(self, *args, **kwargs):
        self.isbn = normalize_isbn(self.isbn)
        self.content_flags = [c for c in self.content_flags if c in ContentCategory.values]
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("inventory:edit", args=[self.pk])

    # Attributes used by RuleSet.check_items --------------------------------
    source = ItemSource.SHELF

    @property
    def is_softcover(self) -> bool:
        return self.format in SOFTCOVER_FORMATS

    @property
    def cover_url(self) -> str:
        if self.cover_id:
            return f"https://covers.openlibrary.org/b/id/{self.cover_id}-M.jpg"
        return ""

    @property
    def openlibrary_url(self) -> str:
        return f"https://openlibrary.org{self.openlibrary_key}" if self.openlibrary_key else ""

    @property
    def first_author(self) -> str:
        return self.authors.split(";")[0].strip()
