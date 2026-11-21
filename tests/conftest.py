from __future__ import annotations

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from shelfpass.correspondence.models import BookRequest, Person, RequestedItem
from shelfpass.facilities.models import Facility, Jurisdiction, Origin
from shelfpass.inventory.models import Book
from shelfpass.orgs.models import Membership, Organization

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def today() -> datetime.date:
    return timezone.localdate()


@pytest.fixture
def org(db) -> Organization:
    return Organization.objects.create(
        name="Test Books to Prisoners",
        return_address="Test Books to Prisoners\nPO Box 1\nTesttown, PA 00010",
        contact_email="hello@test.example",
    )


@pytest.fixture
def other_org(db) -> Organization:
    return Organization.objects.create(
        name="Other Group", return_address="PO Box 2\nElsewhere, OH 00020"
    )


def make_user(
    username: str, org: Organization | None = None, role=Membership.Role.VOLUNTEER, **extra
):
    user = get_user_model().objects.create_user(username=username, password=PASSWORD, **extra)
    if org is not None:
        Membership.objects.create(user=user, organization=org, role=role)
    return user


@pytest.fixture
def coordinator(org):
    return make_user("coord", org, Membership.Role.COORDINATOR, first_name="Casey")


@pytest.fixture
def volunteer(org):
    return make_user("vol", org, Membership.Role.VOLUNTEER)


@pytest.fixture
def client_coord(client, coordinator):
    client.force_login(coordinator)
    return client


@pytest.fixture
def client_vol(client, volunteer):
    client.force_login(volunteer)
    return client


@pytest.fixture
def jurisdiction(db) -> Jurisdiction:
    return Jurisdiction.objects.create(
        code="test-doc",
        name="Test Department of Corrections",
        kind="state",
        state="PA",
        origin=Origin.DATASET,
        rules={
            "paperback_only": True,
            "invoice_required": True,
            "max_books_per_package": 3,
            "banned_content": ["maps-travel"],
            "notes": ["Screened centrally."],
        },
    )


@pytest.fixture
def facility(jurisdiction) -> Facility:
    return Facility.objects.create(
        slug="test-sci",
        name="Test State Correctional Institution",
        kind="state-prison",
        jurisdiction=jurisdiction,
        street="1 Prison Road",
        city="Testville",
        state="PA",
        postal_code="00011",
        origin=Origin.DATASET,
        dataset_path="facilities/pa/test-sci.json",
        rules={"new_only": True, "notes": ["No stickers."]},
    )


@pytest.fixture
def open_facility(db) -> Facility:
    """A facility with no rules at all."""
    return Facility.objects.create(
        slug="easy-county-jail",
        name="Easy County Jail",
        kind="county-jail",
        street="2 Main St",
        city="Easyton",
        state="OH",
        postal_code="00012",
        origin=Origin.DATASET,
    )


def make_book(org, title="The Hobbit", **kwargs) -> Book:
    defaults = {
        "authors": "J.R.R. Tolkien",
        "format": "paperback",
        "condition": "new",
        "category": "fantasy",
        "quantity": 2,
    }
    defaults.update(kwargs)
    return Book.objects.create(organization=org, title=title, **defaults)


@pytest.fixture
def book(org) -> Book:
    return make_book(org)


@pytest.fixture
def person(org, facility) -> Person:
    return Person.objects.create(
        organization=org, name="Marcus Reyes", inmate_id="LK-4821", facility=facility
    )


def make_request(
    org, person, items=(("The Hobbit", "title"),), facility=None, **kwargs
) -> BookRequest:
    req = BookRequest.objects.create(
        organization=org, person=person, facility=facility or person.facility, **kwargs
    )
    for position, (description, kind) in enumerate(items):
        RequestedItem.objects.create(
            request=req, description=description, kind=kind, position=position
        )
    return req


@pytest.fixture
def book_request(org, person) -> BookRequest:
    return make_request(org, person, [("The Hobbit", "title"), ("a dictionary", "topic")])
