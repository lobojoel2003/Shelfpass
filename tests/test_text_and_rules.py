from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from shelfpass.core.text import (
    is_isbn_like,
    normalize_inmate_id,
    normalize_isbn,
    normalize_title,
    similarity,
    tokens,
)
from shelfpass.facilities.rules import BLOCK, INFO, WARN, BannedTitle, RuleSet, title_key
from shelfpass.facilities.vocab import guess_content_flags


@dataclass
class Item:
    title: str = "Dune"
    authors: str = "Frank Herbert"
    isbn: str = ""
    format: str = "paperback"
    condition: str = "new"
    content_flags: list = field(default_factory=list)
    source: str = "shelf"


# ------------------------------------------------------------------ text ---


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0-306-40615-2", "9780306406157"),
        ("978-0-306-40615-7", "9780306406157"),
        ("9780306406157", "9780306406157"),
        ("080442957X", "9780804429573"),
        ("9780306406158", ""),  # bad check digit
        ("not an isbn", ""),
        ("", ""),
    ],
)
def test_normalize_isbn(raw, expected):
    assert normalize_isbn(raw) == expected


def test_isbn_like_and_titles():
    assert is_isbn_like("978-0-306-40615-7")
    assert not is_isbn_like("The Hobbit")
    assert normalize_title("The Hobbit!") == "hobbit"
    assert normalize_title("Économie") == "economie"
    assert tokens("a GED study guide, please") == {"ged", "study", "guide"}
    assert normalize_inmate_id(" ab-12 34 ") == "AB1234"


def test_similarity():
    assert similarity("The Hobbit", "hobbit") == 1.0
    assert similarity("Dune", "Dune: Deluxe Edition") == 0.95
    assert similarity("Dune", "Emma") < 0.5
    assert similarity("", "Dune") == 0.0


def test_guess_content_flags():
    assert guess_content_flags("Rand McNally Road Atlas", "Maps") == ["maps-travel"]
    assert guess_content_flags("Karate basics", "Martial arts") == ["martial-arts"]
    assert guess_content_flags("Pride and Prejudice") == []


# ----------------------------------------------------------------- rules ---


def test_layers_override_and_accumulate():
    rules = RuleSet.from_layers(
        {
            "paperback_only": True,
            "max_books_per_package": 3,
            "notes": ["A"],
            "banned_content": ["maps-travel"],
        },
        {"max_books_per_package": 5, "notes": ["B", "A"], "banned_content": ["tattoo"], "bogus": 1},
        None,
    )
    assert rules.paperback_only
    assert rules.max_books_per_package == 5
    assert rules.notes == ("A", "B")
    assert rules.banned_content == ("maps-travel", "tattoo")
    assert "bogus" not in rules.known


def test_empty_rules_have_unknown_badge():
    rules = RuleSet()
    assert not rules.has_rules
    assert [b.code for b in rules.badges()] == ["unknown"]
    assert rules.summary() == "no rules on file yet"


def test_badges_and_summary():
    rules = RuleSet.from_layers(
        {
            "books_accepted": False,
            "paperback_only": True,
            "new_only": True,
            "vendor_only": True,
            "approved_vendors": ["Publisher"],
            "invoice_required": True,
            "max_books_per_package": 3,
            "max_package_weight_lb": 5,
            "banned_content": ["maps-travel"],
            "banned_titles": ["Some Book", {"title": "Other", "author": "X"}, {"nope": 1}],
            "book_mail_address": ["Center", "PO Box 1", "Town, PA 00001"],
        }
    )
    codes = [b.code for b in rules.badges()]
    assert codes == [
        "no-books",
        "paperback-only",
        "new-only",
        "vendor-only",
        "invoice",
        "max-books",
        "max-weight",
        "content",
        "banned-titles",
        "central-address",
    ]
    assert "paperback only" in rules.summary()
    assert len(rules.banned_titles) == 2
    assert rules.as_dict()["banned_titles"][1] == {"title": "Other", "author": "X"}


def test_hardcover_vendor_badge_only_without_paperback_rule():
    rules = RuleSet.from_layers({"hardcover_vendor_only": True})
    assert [b.code for b in rules.badges()] == ["hardcover-vendor-only"]


def test_check_items_blocks_and_warnings():
    rules = RuleSet.from_layers(
        {
            "paperback_only": True,
            "new_only": True,
            "max_books_per_package": 2,
            "max_package_weight_lb": 1,
            "invoice_required": True,
            "banned_content": ["maps-travel"],
            "banned_titles": [{"title": "The New Jim Crow", "author": "Michelle Alexander"}],
            "book_mail_address": ["A", "B"],
        }
    )
    items = [
        Item(title="Big Book", format="hardcover"),
        Item(title="Old Book", condition="used"),
        Item(title="The New Jim Crow", authors="Michelle Alexander"),
        Item(title="Road Atlas", content_flags=["maps-travel"]),
    ]
    issues = rules.check_items(items, total_weight_oz=40)
    codes = [i.code for i in issues]
    assert {"paperback-only", "new-only", "banned-title", "too-many", "too-heavy"} <= set(codes)
    assert "content" in codes and "invoice" in codes and "central-address" in codes
    levels = [i.level for i in issues]
    assert levels == sorted(levels, key={BLOCK: 0, WARN: 1, INFO: 2}.get)
    assert all(i.is_blocking for i in issues if i.code in {"paperback-only", "too-many"})


def test_vendor_rules():
    vendor_only = RuleSet.from_layers({"vendor_only": True})
    assert [i.code for i in vendor_only.check_items([Item()])] == ["vendor-only"]
    assert vendor_only.check_items([Item(source="vendor")]) == []

    hardcover = RuleSet.from_layers({"hardcover_vendor_only": True})
    assert [i.code for i in hardcover.check_items([Item(format="hardcover")])] == [
        "hardcover-vendor-only"
    ]
    assert hardcover.check_items([Item(format="hardcover", source="vendor")]) == []
    assert hardcover.check_items([Item(format="paperback")]) == []


def test_no_books_accepted():
    rules = RuleSet.from_layers({"books_accepted": False})
    assert rules.check_items([])[0].code == "no-books"
    assert not rules.allows_book("paperback", "new")


@pytest.mark.parametrize(
    ("layer", "fmt", "condition", "allowed"),
    [
        ({}, "hardcover", "used", True),
        ({"paperback_only": True}, "hardcover", "new", False),
        ({"paperback_only": True}, "mass-market", "used", True),
        ({"new_only": True}, "paperback", "used", False),
        ({"hardcover_vendor_only": True}, "hardcover", "new", False),
        ({"vendor_only": True}, "paperback", "new", False),
    ],
)
def test_allows_book(layer, fmt, condition, allowed):
    assert RuleSet.from_layers(layer).allows_book(fmt, condition) is allowed


def test_banned_title_matching():
    by_isbn = BannedTitle(title="Anything", isbn="0306406152")
    assert by_isbn.matches("Something else", isbn="9780306406157")
    assert not by_isbn.matches("Anything", isbn="9780804429573")
    by_title = BannedTitle(title="The New Jim Crow", author="Alexander, Michelle")
    assert by_title.matches("New Jim Crow")
    assert not by_title.matches("New Jim Crow", authors="Somebody Else")
    assert not by_title.matches("Different Book")


def test_recipient_format():
    rules = RuleSet.from_layers({"recipient_format": "{name}, {id}, {housing}"})
    assert rules.format_recipient("Ann Lee", "123", "Unit 4") == "Ann Lee, 123, Unit 4"
    assert rules.format_recipient("Ann Lee", "123") == "Ann Lee, 123"
    broken = RuleSet.from_layers({"recipient_format": "{nope}"})
    assert broken.format_recipient("Ann", "9") == "Ann #9"


def test_title_key():
    assert title_key("Dune", isbn="0-306-40615-2") == "isbn:9780306406157"
    assert title_key("The Hobbit", "J.R.R. Tolkien; Other") == "title:hobbit|j r r tolkien"
