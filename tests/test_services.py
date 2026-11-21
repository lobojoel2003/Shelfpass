from __future__ import annotations

import datetime

import pytest
from django.core.exceptions import ValidationError

from shelfpass.correspondence.history import find_previous, sent_books
from shelfpass.correspondence.models import BookRequest, Person, RequestedItem
from shelfpass.facilities.history import (
    public_reports,
    reason_breakdown,
    rejection_events,
    shipping_stats,
)
from shelfpass.facilities.models import RejectionReport
from shelfpass.inventory.matching import hinted_categories, score_book, suggest_books
from shelfpass.shipping import services
from shelfpass.shipping.models import Package

from .conftest import make_book, make_request

pytestmark = pytest.mark.django_db


def ship(package, today, **kwargs):
    return services.ship(package, shipped_on=today, **kwargs)


# ------------------------------------------------------------- packing ---


def test_start_package_reuses_open_package(book_request, coordinator):
    first = services.start_package(book_request, coordinator)
    assert services.start_package(book_request) == first
    assert services.start_package(book_request, force_new=True) != first
    book_request.refresh_from_db()
    assert book_request.status == BookRequest.Status.PACKING
    assert first.reference == f"P-{first.pk:05d}"


def test_start_package_uses_current_facility(book_request, open_facility):
    person = book_request.person
    person.facility = open_facility
    person.save()
    assert services.start_package(book_request).facility == open_facility


def test_cannot_pack_closed_request(book_request):
    book_request.close("done")
    with pytest.raises(ValidationError):
        services.start_package(book_request)


def test_add_and_remove_book_tracks_stock(book_request, book):
    package = services.start_package(book_request)
    hobbit = book_request.items.get(description="The Hobbit")
    item = services.add_book(package, book, hobbit)
    book.refresh_from_db()
    hobbit.refresh_from_db()
    assert book.quantity == 1
    assert hobbit.status == RequestedItem.Status.PACKED
    assert item.title == "The Hobbit" and item.condition == "new"

    services.remove_item(item)
    book.refresh_from_db()
    hobbit.refresh_from_db()
    assert book.quantity == 2
    assert hobbit.status == RequestedItem.Status.OPEN


def test_add_book_errors(book_request, org, other_org, person):
    package = services.start_package(book_request)
    with pytest.raises(ValidationError, match="out of stock"):
        services.add_book(package, make_book(org, "Gone", quantity=0))
    with pytest.raises(ValidationError, match="another group"):
        services.add_book(package, make_book(other_org, "Theirs"))
    other_request = make_request(org, person)
    with pytest.raises(ValidationError, match="different letter"):
        services.add_book(package, make_book(org, "Mine"), other_request.items.first())


def test_vendor_item(book_request):
    package = services.start_package(book_request)
    item = services.add_vendor_item(
        package, " Dune ", "Frank Herbert", requested_item=book_request.items.first()
    )
    assert item.source == "vendor" and item.condition == "new" and item.title == "Dune"


def test_discard_package_restocks(book_request, book):
    package = services.start_package(book_request)
    services.add_book(package, book)
    services.discard_package(package)
    book.refresh_from_db()
    book_request.refresh_from_db()
    assert book.quantity == 2
    assert not Package.objects.exists()
    assert book_request.status == BookRequest.Status.OPEN


# ------------------------------------------------------------ shipping ---


def test_ship_requires_books_and_override_for_blocking_rules(book_request, org, today):
    package = services.start_package(book_request)
    with pytest.raises(ValidationError, match="at least one book"):
        ship(package, today)

    used = make_book(org, "Used Hardcover", format="hardcover", condition="used")
    services.add_book(package, used)
    with pytest.raises(ValidationError, match="breaks the facility's rules"):
        ship(package, today)

    ship(
        package,
        today,
        override_note="Testing",
        carrier="usps-media",
        postage_cents=476,
        weight_oz=20,
    )
    package.refresh_from_db()
    assert package.status == Package.Status.SHIPPED
    assert package.postage_display == "$4.76"
    assert package.request.status == BookRequest.Status.SHIPPED
    with pytest.raises(ValidationError, match="already shipped"):
        services.add_vendor_item(package, "Late")


def test_deliver_and_return_lifecycle(book_request, book, today):
    package = services.start_package(book_request)
    item = services.add_book(package, book, book_request.items.first())
    with pytest.raises(ValidationError):
        services.mark_delivered(package, today)
    with pytest.raises(ValidationError):
        services.log_return(package, "content", today)
    ship(package, today)
    services.mark_delivered(package, today)
    assert package.status == Package.Status.DELIVERED

    record = services.log_return(
        package, "hardcover", today, "Stamped", flagged_item=item, restock=True
    )
    package.refresh_from_db()
    book.refresh_from_db()
    book_request.refresh_from_db()
    assert package.status == Package.Status.RETURNED
    assert record.restocked and book.quantity == 2
    assert book_request.status == BookRequest.Status.RETURNED
    assert book_request.items.first().status == RequestedItem.Status.OPEN
    assert str(record).startswith("Return of")


def test_lost_package_is_not_restocked(book_request, book, today, other_org):
    package = services.start_package(book_request)
    services.add_book(package, book)
    ship(package, today)
    other_item = services.start_package(
        make_request(book_request.organization, book_request.person), force_new=True
    )
    with pytest.raises(ValidationError, match="isn't in this package"):
        services.log_return(
            package, "content", today, flagged_item=services.add_vendor_item(other_item, "X")
        )
    record = services.log_return(package, "no-response", today)
    book.refresh_from_db()
    assert record.is_lost and not record.restocked and book.quantity == 1
    assert Package.objects.get(pk=package.pk).status == Package.Status.LOST


def test_request_close_and_reopen(book_request):
    book_request.close("Nothing on the shelf")
    assert book_request.is_closed and book_request.refresh_status() == BookRequest.Status.CLOSED
    book_request.reopen()
    assert book_request.status == BookRequest.Status.OPEN


# ------------------------------------------------------------- history ---


def test_sent_books_and_duplicates(book_request, book, org, today):
    package = services.start_package(book_request)
    services.add_book(package, book)
    ship(package, today)
    history = sent_books(book_request.person)
    assert [s.title for s in history] == ["The Hobbit"]
    assert find_previous(history, "the hobbit") is not None
    assert find_previous(history, "Dune") is None
    assert sent_books(book_request.person, exclude_package_id=package.pk) == []
    services.log_return(package, "content", today)
    assert sent_books(book_request.person) == []


def test_rejection_events_merge_and_privacy(book_request, book, org, other_org, facility, today):
    package = services.start_package(book_request)
    services.add_book(package, book)
    ship(package, today)
    services.log_return(package, "used-book", today, "Secret note with a name")
    RejectionReport.objects.create(
        external_id="abc",
        facility=facility,
        month=today.replace(day=1),
        reason="content",
        title="Atlas",
        reporter="Elsewhere",
    )

    own = rejection_events(facility, viewer_org=org)
    assert [e.reason for e in own] == ["used-book", "content"]
    assert own[0].detail == "Secret note with a name" and own[0].source == "Your group"
    assert own[0].title == "The Hobbit"  # single-book package -> the book is known
    assert own[0].format_label == "new paperback"

    theirs = rejection_events(
        facility, viewer_org=other_org, since=today - datetime.timedelta(days=1)
    )
    assert theirs[0].detail == "" and theirs[0].source == "Another group on this site"
    assert len(rejection_events(limit=1)) == 1

    breakdown = reason_breakdown(own)
    assert {r.code for r in breakdown} == {"used-book", "content"} and breakdown[0].percent == 50
    assert shipping_stats(facility) == {"shipped": 1, "returned": 1, "rate": 100}


def test_public_reports_respect_sharing(book_request, book, org, facility, today):
    package = services.start_package(book_request)
    item = services.add_book(package, book)
    ship(package, today)
    services.log_return(package, "used-book", today, "private", flagged_item=item)
    reports = public_reports()
    assert reports == [
        {
            "facility": "test-sci",
            "month": today.strftime("%Y-%m"),
            "reason": "used-book",
            "book": {
                "title": "The Hobbit",
                "authors": "J.R.R. Tolkien",
                "format": "paperback",
                "condition": "new",
            },
        }
    ]
    assert "private" not in str(reports) and "Marcus" not in str(reports)
    org.share_rejections = False
    org.save()
    assert public_reports() == []


# ------------------------------------------------------------ matching ---


def test_hinted_categories():
    assert hinted_categories("a GED study guide") == ["education"]
    assert "reference" in hinted_categories("Webster's dictionary please")
    assert hinted_categories("something") == []


def test_suggest_books_ranks_and_filters(org, facility, other_org):
    rules = facility.ruleset  # paperback only + new only
    good = make_book(
        org, "GED Test Prep Plus", authors="Kaplan", category="education", condition="new"
    )
    used = make_book(org, "GED Prep (used)", category="education", condition="used")
    make_book(org, "GED Out of Stock", category="education", quantity=0)
    make_book(other_org, "GED Theirs", category="education")
    make_book(org, "Unrelated Cookbook", category="other")

    suggestions = suggest_books(org, "GED study guide", rules=rules)
    titles = [s.book.title for s in suggestions]
    assert titles == ["GED Test Prep Plus", "GED Prep (used)"]
    assert suggestions[0].allowed and suggestions[0].recommended
    assert not suggestions[1].allowed
    assert suggest_books(org, "GED", rules=rules, exclude_ids={good.pk, used.pk}) == []
    assert suggest_books(org, "  ") == []


def test_score_book_author_and_title(org):
    book = make_book(org, "The Way of Kings", authors="Brandon Sanderson")
    score, reason = score_book(book, "Way of Kings", "Sanderson")
    assert score > 1 and reason == "Title and author match"
    score, reason = score_book(book, "anything by", "Brandon Sanderson")
    assert reason == "Same author"


def test_suggestions_flag_restricted_content(org, facility):
    make_book(org, "Road Atlas", category="reference", content_flags=["maps-travel"])
    [suggestion] = suggest_books(org, "road atlas", rules=facility.ruleset)
    assert suggestion.restricted and not suggestion.recommended


# --------------------------------------------------------------- models ---


def test_model_helpers(org, facility, person, book):
    assert person.inmate_id_normalized == "LK4821"
    assert str(person) == "Marcus Reyes #LK-4821"
    assert facility.address_lines == ["1 Prison Road", "Testville, PA 00011"]
    assert facility.book_address_lines[0] == facility.name
    assert facility.ruleset.paperback_only and facility.ruleset.new_only
    assert str(facility) == "Test State Correctional Institution (Testville, PA)"
    assert org.sender_lines[0] == org.name and len(org.sender_lines) == 3
    org.return_address = "PO Box 9"
    assert org.sender_lines == [org.name, "PO Box 9"]
    assert book.cover_url == "" and book.openlibrary_url == "" and book.is_softcover
    book.cover_id, book.openlibrary_key = "123", "/works/OL1W"
    assert book.cover_url.endswith("/123-M.jpg") and book.openlibrary_url.endswith("/works/OL1W")
    assert str(book) == "The Hobbit — J.R.R. Tolkien"
    assert BookRequest(pk=None).reference == "R-new"
    assert Package(pk=None).reference == "P-new"
    assert Person.objects.get(pk=person.pk).get_absolute_url().endswith(f"/people/{person.pk}/")
