"""Facility mail rules: merging, summarising and checking packages against them.

Rules are stored as plain JSON (the same shape as the open dataset) on both
:class:`~shelfpass.facilities.models.Jurisdiction` (system-wide, e.g. a state
DOC) and :class:`~shelfpass.facilities.models.Facility` (local overrides).
:class:`RuleSet` is the merged, typed view the rest of the app works with.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from shelfpass.core.text import normalize_isbn, normalize_title, similarity
from shelfpass.facilities.vocab import (
    SOFTCOVER_FORMATS,
    BookCondition,
    BookFormat,
    ContentCategory,
    ItemSource,
)

BLOCK = "block"
WARN = "warn"
INFO = "info"
LEVEL_ORDER = {BLOCK: 0, WARN: 1, INFO: 2}

DEFAULT_RECIPIENT_FORMAT = "{name} #{id}"

#: Keys understood in a dataset ``rules`` object, with their Python type.
RULE_KEYS: dict[str, type] = {
    "books_accepted": bool,
    "paperback_only": bool,
    "new_only": bool,
    "vendor_only": bool,
    "hardcover_vendor_only": bool,
    "approved_vendors": list,
    "invoice_required": bool,
    "max_books_per_package": int,
    "max_package_weight_lb": float,
    "banned_content": list,
    "banned_titles": list,
    "notes": list,
    "recipient_format": str,
    "book_mail_address": list,
}

#: List-valued keys that accumulate across layers instead of overriding.
_ACCUMULATING = {"banned_content", "banned_titles", "notes"}


@dataclass(frozen=True)
class BannedTitle:
    title: str
    author: str = ""
    isbn: str = ""
    note: str = ""

    def matches(self, title: str, authors: str = "", isbn: str = "") -> bool:
        mine, theirs = normalize_isbn(self.isbn), normalize_isbn(isbn)
        if mine and theirs:
            return mine == theirs
        if similarity(self.title, title) < 0.9:
            return False
        if self.author and authors:
            return similarity(self.author.split(",")[0], authors.split(";")[0]) >= 0.6
        return True


@dataclass(frozen=True)
class Badge:
    code: str
    label: str
    level: str = INFO
    detail: str = ""


@dataclass(frozen=True)
class Issue:
    level: str
    code: str
    message: str
    item_index: int | None = None

    @property
    def is_blocking(self) -> bool:
        return self.level == BLOCK


class CheckableItem(Protocol):
    title: str
    authors: str
    isbn: str
    format: str
    condition: str
    content_flags: Sequence[str]
    source: str


@dataclass(frozen=True)
class RuleSet:
    books_accepted: bool = True
    paperback_only: bool = False
    new_only: bool = False
    vendor_only: bool = False
    hardcover_vendor_only: bool = False
    approved_vendors: tuple[str, ...] = ()
    invoice_required: bool = False
    max_books_per_package: int | None = None
    max_package_weight_lb: float | None = None
    banned_content: tuple[str, ...] = ()
    banned_titles: tuple[BannedTitle, ...] = ()
    notes: tuple[str, ...] = ()
    recipient_format: str = DEFAULT_RECIPIENT_FORMAT
    book_mail_address: tuple[str, ...] = ()
    known: frozenset[str] = field(default_factory=frozenset)

    # ---------------------------------------------------------- building ---

    @classmethod
    def from_layers(cls, *layers: dict | None) -> RuleSet:
        """Merge rule dicts, later layers overriding earlier ones."""
        merged: dict[str, object] = {}
        for layer in layers:
            for key, value in (layer or {}).items():
                if key not in RULE_KEYS or value is None:
                    continue
                if key in _ACCUMULATING and key in merged:
                    existing = list(merged[key])  # type: ignore[arg-type]
                    merged[key] = existing + [v for v in value if v not in existing]
                else:
                    merged[key] = value
        return cls._from_merged(merged)

    @classmethod
    def _from_merged(cls, data: dict[str, object]) -> RuleSet:
        def as_tuple(key: str) -> tuple[str, ...]:
            return tuple(str(v).strip() for v in data.get(key, ()) if str(v).strip())  # type: ignore[union-attr]

        banned_titles = []
        for entry in data.get("banned_titles", ()):  # type: ignore[union-attr]
            if isinstance(entry, str):
                banned_titles.append(BannedTitle(title=entry))
            elif isinstance(entry, dict) and entry.get("title"):
                banned_titles.append(
                    BannedTitle(
                        title=str(entry["title"]),
                        author=str(entry.get("author", "")),
                        isbn=str(entry.get("isbn", "")),
                        note=str(entry.get("note", "")),
                    )
                )

        max_books = data.get("max_books_per_package")
        max_weight = data.get("max_package_weight_lb")
        return cls(
            books_accepted=bool(data.get("books_accepted", True)),
            paperback_only=bool(data.get("paperback_only", False)),
            new_only=bool(data.get("new_only", False)),
            vendor_only=bool(data.get("vendor_only", False)),
            hardcover_vendor_only=bool(data.get("hardcover_vendor_only", False)),
            approved_vendors=as_tuple("approved_vendors"),
            invoice_required=bool(data.get("invoice_required", False)),
            max_books_per_package=int(max_books) if max_books else None,  # type: ignore[call-overload]
            max_package_weight_lb=float(max_weight) if max_weight else None,  # type: ignore[arg-type]
            banned_content=as_tuple("banned_content"),
            banned_titles=tuple(banned_titles),
            notes=as_tuple("notes"),
            recipient_format=str(data.get("recipient_format") or DEFAULT_RECIPIENT_FORMAT),
            book_mail_address=as_tuple("book_mail_address"),
            known=frozenset(data),
        )

    # --------------------------------------------------------- presenting ---

    @property
    def has_rules(self) -> bool:
        return bool(self.known - {"notes", "recipient_format"}) or bool(self.notes)

    def content_labels(self) -> list[str]:
        labels = dict(ContentCategory.choices)
        return [labels.get(code, code) for code in self.banned_content]

    def badges(self) -> list[Badge]:
        """Short, scannable summary chips ("Paperback only", "Max 3 per package")."""
        out: list[Badge] = []
        if not self.books_accepted:
            out.append(Badge("no-books", "Does not accept book packages", BLOCK))
        if self.paperback_only:
            out.append(
                Badge("paperback-only", "Paperback only", WARN, "No hardcovers or spiral bindings.")
            )
        elif self.hardcover_vendor_only:
            out.append(
                Badge(
                    "hardcover-vendor-only",
                    "Hardcovers only from publisher or bookstore",
                    WARN,
                    "Send hardcovers directly from a publisher, bookstore or book club.",
                )
            )
        if self.new_only:
            out.append(Badge("new-only", "No used books", WARN, "New books only."))
        if self.vendor_only:
            vendors = ", ".join(self.approved_vendors) or "an approved vendor"
            out.append(
                Badge("vendor-only", "Approved vendors only", BLOCK, f"Ship from {vendors}.")
            )
        if self.invoice_required:
            out.append(
                Badge("invoice", "Invoice required", INFO, "Enclose the packing slip / invoice.")
            )
        if self.max_books_per_package:
            out.append(Badge("max-books", f"Max {self.max_books_per_package} per package", WARN))
        if self.max_package_weight_lb:
            out.append(
                Badge("max-weight", f"Max {self.max_package_weight_lb:g} lb per package", WARN)
            )
        if self.banned_content:
            out.append(
                Badge("content", "Content restrictions", WARN, "; ".join(self.content_labels()))
            )
        if self.banned_titles:
            n = len(self.banned_titles)
            out.append(Badge("banned-titles", f"{n} banned title{'s' if n != 1 else ''}", WARN))
        if self.book_mail_address:
            out.append(
                Badge(
                    "central-address",
                    "Ship to central processing",
                    INFO,
                    " / ".join(self.book_mail_address),
                )
            )
        if not out and not self.notes:
            out.append(Badge("unknown", "No rules on file yet", INFO))
        return out

    def summary(self) -> str:
        """One-line summary, e.g. "paperback only, no used books, max 3 per package"."""
        return ", ".join(b.label[0].lower() + b.label[1:] for b in self.badges())

    def format_recipient(self, name: str, inmate_id: str, housing: str = "") -> str:
        fmt = self.recipient_format or DEFAULT_RECIPIENT_FORMAT
        try:
            line = fmt.format(name=name, id=inmate_id, housing=housing)
        except (KeyError, IndexError, ValueError):
            line = DEFAULT_RECIPIENT_FORMAT.format(name=name, id=inmate_id)
        return " ".join(line.replace(", ,", ",").split()).strip(" ,")

    def as_dict(self) -> dict[str, object]:
        return {
            "books_accepted": self.books_accepted,
            "paperback_only": self.paperback_only,
            "new_only": self.new_only,
            "vendor_only": self.vendor_only,
            "hardcover_vendor_only": self.hardcover_vendor_only,
            "approved_vendors": list(self.approved_vendors),
            "invoice_required": self.invoice_required,
            "max_books_per_package": self.max_books_per_package,
            "max_package_weight_lb": self.max_package_weight_lb,
            "banned_content": list(self.banned_content),
            "banned_titles": [{k: v for k, v in vars(t).items() if v} for t in self.banned_titles],
            "notes": list(self.notes),
            "recipient_format": self.recipient_format,
            "book_mail_address": list(self.book_mail_address),
        }

    # ------------------------------------------------------------ checking ---

    def allows_book(self, format: str, condition: str) -> bool:
        """Quick filter for shelf suggestions (format and condition only)."""
        if not self.books_accepted or self.vendor_only:
            return False
        if self.paperback_only and format not in SOFTCOVER_FORMATS:
            return False
        if self.hardcover_vendor_only and format == BookFormat.HARDCOVER:
            return False
        return not (self.new_only and condition == BookCondition.USED)

    def check_items(
        self, items: Sequence[CheckableItem], total_weight_oz: float | None = None
    ) -> list[Issue]:
        """Every rule problem with a package's contents, most serious first."""
        issues: list[Issue] = []
        if not self.books_accepted:
            issues.append(Issue(BLOCK, "no-books", "This facility does not accept book packages."))

        for index, item in enumerate(items):
            issues.extend(self._check_item(index, item))

        if self.max_books_per_package and len(items) > self.max_books_per_package:
            issues.append(
                Issue(
                    BLOCK,
                    "too-many",
                    f"{len(items)} books in this package; the facility allows at most "
                    f"{self.max_books_per_package}. Split it into another package.",
                )
            )
        if self.max_package_weight_lb and total_weight_oz:
            limit_oz = self.max_package_weight_lb * 16
            if total_weight_oz > limit_oz:
                issues.append(
                    Issue(
                        BLOCK,
                        "too-heavy",
                        f"Package weighs {total_weight_oz / 16:.1f} lb; the limit is "
                        f"{self.max_package_weight_lb:g} lb.",
                    )
                )
        if items and self.invoice_required:
            issues.append(
                Issue(
                    INFO, "invoice", "Enclose the packing slip — this facility requires an invoice."
                )
            )
        if items and self.book_mail_address:
            issues.append(
                Issue(
                    INFO,
                    "central-address",
                    "Books go to the central processing address, which is printed on the label.",
                )
            )
        return sort_issues(issues)

    def _check_item(self, index: int, item: CheckableItem) -> Iterable[Issue]:
        name = f"“{item.title}”"
        from_vendor = item.source == ItemSource.VENDOR
        if self.paperback_only and item.format not in SOFTCOVER_FORMATS:
            kind = dict(BookFormat.choices).get(item.format, item.format).lower()
            yield Issue(BLOCK, "paperback-only", f"{name} is {kind}; paperbacks only.", index)
        if self.new_only and item.condition == BookCondition.USED:
            yield Issue(
                BLOCK, "new-only", f"{name} is used; this facility only accepts new books.", index
            )
        if self.vendor_only and not from_vendor:
            vendors = ", ".join(self.approved_vendors) or "an approved vendor"
            yield Issue(BLOCK, "vendor-only", f"{name} must ship directly from {vendors}.", index)
        elif (
            self.hardcover_vendor_only
            and not self.paperback_only
            and item.format == BookFormat.HARDCOVER
            and not from_vendor
        ):
            yield Issue(
                BLOCK,
                "hardcover-vendor-only",
                f"{name} is a hardcover; hardcovers must come from a publisher or bookstore.",
                index,
            )
        for banned in self.banned_titles:
            if banned.matches(item.title, item.authors, item.isbn):
                note = f" ({banned.note})" if banned.note else ""
                yield Issue(
                    BLOCK, "banned-title", f"{name} is on this facility's banned list{note}.", index
                )
                break
        flagged = [c for c in item.content_flags if c in self.banned_content]
        if flagged:
            labels = dict(ContentCategory.choices)
            what = ", ".join(labels.get(c, c).lower() for c in flagged)
            yield Issue(WARN, "content", f"{name} may be restricted here: {what}.", index)


def sort_issues(issues: Iterable[Issue]) -> list[Issue]:
    return sorted(issues, key=lambda i: (LEVEL_ORDER.get(i.level, 9), i.item_index or -1))


def title_key(title: str, authors: str = "", isbn: str = "") -> str:
    """Stable identity for "the same book" across editions when ISBNs are missing."""
    normalized = normalize_isbn(isbn)
    if normalized:
        return f"isbn:{normalized}"
    first_author = normalize_title((authors or "").split(";")[0])
    return f"title:{normalize_title(title)}|{first_author}"
