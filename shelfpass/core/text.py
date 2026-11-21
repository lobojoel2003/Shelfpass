"""Small text helpers shared by matching, duplicate detection and imports."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_ARTICLES = ("the ", "a ", "an ")
_NON_WORD = re.compile(r"[^a-z0-9]+")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "any",
        "by",
        "for",
        "from",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "please",
        "some",
        "the",
        "to",
        "with",
        "book",
        "books",
        "series",
        "copy",
        "volume",
        "vol",
        "edition",
    ]
)


def fold(value: str) -> str:
    """Lower-case and strip accents, keeping only ASCII letters, digits and spaces."""
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    return _NON_WORD.sub(" ", value).strip()


def normalize_title(value: str) -> str:
    """Normalised form of a title for equality checks ("The Hobbit!" -> "hobbit")."""
    folded = fold(value)
    for article in _ARTICLES:
        if folded.startswith(article):
            folded = folded[len(article) :]
            break
    return folded


def tokens(value: str) -> set[str]:
    """Meaningful words of a free-text request ("a GED study guide" -> {ged, study, guide})."""
    return {word for word in fold(value).split() if word not in _STOPWORDS and len(word) > 1}


def similarity(a: str, b: str) -> float:
    """Similarity in [0, 1] between two titles, robust to subtitles and articles."""
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    shorter, longer = sorted((na, nb), key=len)
    if len(shorter) >= 4 and longer.startswith(shorter + " "):
        return 0.95
    return SequenceMatcher(None, na, nb).ratio()


# ------------------------------------------------------------------ ISBNs ---

_ISBN_CHARS = re.compile(r"[^0-9Xx]")


def _isbn10_valid(digits: str) -> bool:
    if not re.fullmatch(r"\d{9}[\dX]", digits):
        return False
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(digits))
    return total % 11 == 0


def _isbn13_check_digit(first12: str) -> str:
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(first12))
    return str((10 - total % 10) % 10)


def _isbn13_valid(digits: str) -> bool:
    return bool(re.fullmatch(r"\d{13}", digits)) and _isbn13_check_digit(digits[:12]) == digits[12]


def normalize_isbn(value: str) -> str:
    """Return a valid ISBN-13 for any valid ISBN-10/13 input, or ``""``."""
    digits = _ISBN_CHARS.sub("", value or "").upper()
    if len(digits) == 10 and _isbn10_valid(digits):
        core = "978" + digits[:9]
        return core + _isbn13_check_digit(core)
    if len(digits) == 13 and _isbn13_valid(digits):
        return digits
    return ""


def is_isbn_like(value: str) -> bool:
    """True when the text looks like someone typed an ISBN (rather than a title)."""
    digits = _ISBN_CHARS.sub("", value or "")
    return len(digits) in (10, 13) and len(digits) >= len((value or "").strip()) - 4


def normalize_inmate_id(value: str) -> str:
    """Canonical form of a prison ID number for matching ("AB-1234 " -> "AB1234")."""
    return re.sub(r"[^0-9A-Za-z]", "", value or "").upper()
