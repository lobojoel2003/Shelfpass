"""Suggest books from the shelf for a requested item."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q

from shelfpass.core.text import fold, similarity, tokens
from shelfpass.facilities.rules import RuleSet
from shelfpass.inventory.models import CATEGORY_HINTS, Book, Category

MIN_SCORE = 0.3


@dataclass
class Suggestion:
    book: Book
    score: float
    reason: str
    allowed: bool
    previously_sent: object | None = None  # a correspondence.history.SentBook

    restricted: bool = False  # content the facility may restrict (warning, not a block)

    @property
    def recommended(self) -> bool:
        return self.allowed and not self.restricted and self.previously_sent is None


def hinted_categories(text: str) -> list[str]:
    """Shelf categories a free-text request points at ("GED study guide" -> education)."""
    folded = f" {fold(text)} "
    found = []
    for category, words in CATEGORY_HINTS.items():
        if any(f" {w} " in folded for w in words):
            found.append(str(category))
    return found


def _same_author(wanted: str, authors: str) -> bool:
    """ "Sanderson" matches "Brandon Sanderson"; "Tolkien" matches "J.R.R. Tolkien"."""
    surnames = {w for w in tokens(wanted) if len(w) > 2}
    if surnames & tokens(authors):
        return True
    return similarity(wanted, authors.split(";")[0]) >= 0.7


def _book_tokens(book: Book) -> set[str]:
    return tokens(" ".join([book.title, book.authors, " ".join(book.subjects or [])]))


def score_book(book: Book, text: str, author: str = "", categories: list[str] | None = None):
    """Return ``(score, reason)`` for how well a shelf book answers the request."""
    categories = categories if categories is not None else hinted_categories(text)
    wanted = tokens(f"{text} {author}")
    title_score = similarity(text, book.title)
    overlap = len(wanted & _book_tokens(book)) / len(wanted) if wanted else 0.0

    score = max(title_score, overlap * 0.8)
    reason = (
        "Title match" if title_score >= overlap * 0.8 and title_score >= 0.6 else "Keyword match"
    )
    if author and book.authors and _same_author(author, book.authors):
        score += 0.3
        reason = "Title and author match" if title_score >= 0.6 else "Same author"
    if book.category in categories:
        score += 0.35
        if score - 0.35 < MIN_SCORE:
            reason = f"Shelved under {Category(book.category).label}"
    return min(score, 1.5), reason


def suggest_books(
    organization,
    text: str,
    author: str = "",
    rules: RuleSet | None = None,
    limit: int = 4,
    exclude_ids: set[int] | None = None,
) -> list[Suggestion]:
    """Best in-stock shelf matches, allowed-by-the-rules first."""
    rules = rules or RuleSet()
    categories = hinted_categories(text)
    words = tokens(f"{text} {author}")
    if not words and not categories:
        return []

    filters = Q(category__in=categories) if categories else Q()
    for word in words:
        filters |= Q(title__icontains=word) | Q(authors__icontains=word)
    candidates = (
        Book.objects.in_stock()
        .filter(organization=organization)
        .filter(filters)
        .exclude(pk__in=exclude_ids or ())[:300]
    )

    suggestions = []
    for book in candidates:
        score, reason = score_book(book, text, author, categories)
        if score >= MIN_SCORE:
            restricted = bool(set(book.content_flags or ()) & set(rules.banned_content))
            suggestions.append(
                Suggestion(
                    book,
                    score,
                    reason,
                    rules.allows_book(book.format, book.condition),
                    restricted=restricted,
                )
            )
    suggestions.sort(key=lambda s: (not s.allowed, s.restricted, -s.score, s.book.title))
    return suggestions[:limit]
