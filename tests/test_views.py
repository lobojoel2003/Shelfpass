from __future__ import annotations

import datetime
import io
import json

import pytest
from django.urls import reverse

from shelfpass.correspondence.models import BookRequest, Person, RequestedItem
from shelfpass.facilities.models import Facility, Origin
from shelfpass.inventory.models import Book
from shelfpass.orgs.middleware import SESSION_KEY
from shelfpass.orgs.models import Membership
from shelfpass.shipping import services
from shelfpass.shipping.models import Package, Return

from .conftest import make_book, make_request, make_user

pytestmark = pytest.mark.django_db


def intake_data(facility, **overrides):
    data = {
        "name": "Ana Torres",
        "inmate_id": "ZX-1001",
        "facility": facility.pk,
        "housing": "Unit 3",
        "received_on": datetime.date.today().isoformat(),
        "letter_notes": "Wants to study for the GED",
        "items-TOTAL_FORMS": "3",
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "0",
        "items-MAX_NUM_FORMS": "25",
        "items-0-description": "GED study guide",
        "items-0-author": "",
        "items-0-kind": "topic",
        "items-1-description": "The Hobbit",
        "items-1-author": "Tolkien",
        "items-1-kind": "title",
        "items-2-description": "",
        "items-2-kind": "title",
    }
    data.update(overrides)
    return data


# --------------------------------------------------------- auth/access ---


def test_login_required(client):
    response = client.get(reverse("core:dashboard"))
    assert response.status_code == 302 and "/accounts/login/" in response["Location"]


def test_login_page_and_user_without_group(client, db):
    assert client.get(reverse("login")).status_code == 200
    client.force_login(make_user("lonely"))
    response = client.get(reverse("core:dashboard"))
    assert response.status_code == 403
    assert b"not in a group yet" in response.content


def test_dashboard(client_coord, book_request):
    response = client_coord.get(reverse("core:dashboard"))
    assert response.status_code == 200
    assert b"Marcus Reyes" in response.content
    assert response.context["stats"]["waiting"] == 1


def test_health_and_version(client, monkeypatch):
    from shelfpass import version

    version.get_build_info.cache_clear()
    monkeypatch.setenv("SHELFPASS_BUILD_NUMBER", "42")
    monkeypatch.setenv("SHELFPASS_COMMIT", "abcdef1234567")
    try:
        health = client.get(reverse("healthz")).json()
        assert health["status"] == "ok" and health["database"] == "ok"
        assert health["build_number"] == "42"
        data = client.get(reverse("version")).json()
        assert data["label"] == "v1.0.0 · build 42 · abcdef1"
    finally:
        version.get_build_info.cache_clear()


def test_healthz_reports_database_failure(client, monkeypatch):
    from django.db import connection

    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(connection, "cursor", boom)
    response = client.get(reverse("healthz"))
    assert response.status_code == 503 and response.json()["database"] == "unavailable"


def test_build_info_file(tmp_path, monkeypatch):
    from shelfpass import version

    path = tmp_path / "BUILD_INFO.json"
    path.write_text(
        json.dumps({"build_number": "7", "commit": "1234567890", "build_date": "2026-11-21"})
    )
    monkeypatch.setenv("SHELFPASS_BUILD_INFO", str(path))
    for name in ("SHELFPASS_BUILD_NUMBER", "SHELFPASS_COMMIT", "SHELFPASS_BUILD_DATE"):
        monkeypatch.delenv(name, raising=False)
    version.get_build_info.cache_clear()
    try:
        info = version.get_build_info()
        assert (info.build_number, info.short_commit, info.build_date) == (
            "7",
            "1234567",
            "2026-11-21",
        )
        path.write_text("{broken")
        version.get_build_info.cache_clear()
        assert version.get_build_info().label == "v1.0.0 · dev build"
    finally:
        version.get_build_info.cache_clear()


def test_error_pages(client_coord):
    response = client_coord.get("/requests/999999/")
    assert response.status_code == 404
    from shelfpass.core import views

    assert views.error_403(response.wsgi_request).status_code == 403
    assert views.error_500(response.wsgi_request).status_code == 500


# --------------------------------------------------------------- intake ---


def test_intake_creates_person_and_request(client_coord, facility, coordinator):
    response = client_coord.get(reverse("correspondence:intake") + f"?facility={facility.pk}")
    assert response.status_code == 200
    assert f'data-slug="{facility.slug}"'.encode() in response.content

    response = client_coord.post(reverse("correspondence:intake"), intake_data(facility))
    req = BookRequest.objects.get()
    assert response.status_code == 302 and response["Location"] == req.get_absolute_url()
    assert req.person.name == "Ana Torres" and req.person.inmate_id_normalized == "ZX1001"
    assert req.created_by == coordinator
    assert list(req.items.values_list("description", "kind")) == [
        ("GED study guide", "topic"),
        ("The Hobbit", "title"),
    ]


def test_intake_reuses_person_by_id_and_facility(client_coord, facility, person):
    data = intake_data(facility, name="Marcus R.", inmate_id="lk 4821", housing="")
    response = client_coord.post(reverse("correspondence:intake"), {**data, "add_another": "1"})
    assert response["Location"] == reverse("correspondence:intake")
    assert Person.objects.count() == 1
    person.refresh_from_db()
    assert person.name == "Marcus R." and person.requests.count() == 1


def test_intake_with_person_id_records_transfer(client_coord, facility, open_facility, person):
    data = intake_data(open_facility, name="Marcus Reyes", inmate_id="LK-4821", person_id=person.pk)
    client_coord.post(reverse("correspondence:intake"), data)
    person.refresh_from_db()
    assert person.facility == open_facility


def test_intake_prefill_from_person(client_coord, person):
    response = client_coord.get(reverse("correspondence:intake") + f"?person={person.pk}")
    assert response.context["form"].initial["name"] == "Marcus Reyes"
    assert (
        client_coord.get(reverse("correspondence:intake") + "?person=abc&facility=x").status_code
        == 200
    )


def test_intake_validation(client_coord, facility, other_org):
    future = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
    data = intake_data(
        facility, received_on=future, **{"items-0-description": "", "items-1-description": ""}
    )
    response = client_coord.post(reverse("correspondence:intake"), data)
    assert response.status_code == 200
    assert "future" in str(response.context["form"].errors)
    assert "at least one" in str(response.context["items"].non_form_errors())

    stranger = Person.objects.create(organization=other_org, name="X", inmate_id="1")
    response = client_coord.post(
        reverse("correspondence:intake"), intake_data(facility, person_id=stranger.pk)
    )
    assert "no longer exists" in str(response.context["form"].errors)
    assert not BookRequest.objects.exists()


def test_person_lookup(client_coord, person, book_request, book, other_org):
    package = services.start_package(book_request)
    services.add_book(package, book)
    Person.objects.create(organization=other_org, name="Hidden", inmate_id="LK4821")
    data = client_coord.get(
        reverse("correspondence:person_lookup"), {"inmate_id": "lk-4821"}
    ).json()
    assert [m["name"] for m in data["matches"]] == ["Marcus Reyes"]
    assert data["matches"][0]["sent"][0]["title"] == "The Hobbit"
    assert client_coord.get(reverse("correspondence:person_lookup"), {"inmate_id": "1"}).json() == {
        "matches": []
    }


# ------------------------------------------------------- request detail ---


def test_request_detail_shows_suggestions_and_duplicates(
    client_coord, org, person, facility, today
):
    old = make_request(org, person, [("The Hobbit", "title")])
    hobbit = make_book(org, "The Hobbit", quantity=3)
    package = services.start_package(old)
    services.add_book(package, hobbit)
    services.ship(package, shipped_on=today)

    new = make_request(org, person, [("The Hobbit", "title"), ("hobbit", "topic")])
    response = client_coord.get(new.get_absolute_url())
    assert response.status_code == 200
    rows = response.context["rows"]
    assert rows[0].previously_sent.package_reference == package.reference
    assert rows[1].suggestions[0].book == hobbit
    assert rows[1].suggestions[0].previously_sent is not None
    assert b"Already sent" in response.content


def test_request_flow_pack_ship_return(client_coord, book_request, book, org):
    item = book_request.items.get(description="The Hobbit")
    url = reverse("shipping:pack_book", args=[book_request.pk])
    response = client_coord.post(url, {"book": book.pk, "item": item.pk})
    assert response.status_code == 302 and f"#item-{item.pk}" in response["Location"]
    package = Package.objects.get()
    assert package.items.count() == 1

    detail = client_coord.get(book_request.get_absolute_url())
    assert detail.context["open_package"] == package

    assert client_coord.post(url, {"book": "nope"}).status_code == 404
    response = client_coord.post(
        url, {"book": make_book(org, "None left", quantity=0).pk}, follow=True
    )
    assert b"out of stock" in response.content

    page = client_coord.get(package.get_absolute_url(), {"q": "hob"})
    assert page.status_code == 200 and page.context["issues"]

    response = client_coord.post(
        reverse("shipping:ship", args=[package.pk]),
        {"shipped_on": "2001-01-01", "carrier": "usps-media", "postage": "4.10"},
    )
    package.refresh_from_db()
    assert package.status == "shipped" and package.postage_cents == 410

    response = client_coord.get(reverse("shipping:log_return", args=[package.pk]))
    assert response.status_code == 200
    client_coord.post(
        reverse("shipping:log_return", args=[package.pk]),
        {"reason": "content", "received_on": "2001-02-01", "detail": "Denied", "restock": "on"},
    )
    assert Return.objects.get().reason == "content"
    response = client_coord.get(reverse("shipping:log_return", args=[package.pk]))
    assert response.status_code == 302  # already logged
    assert client_coord.get(reverse("shipping:returns")).status_code == 200


def test_ship_errors_and_deliver(client_coord, book_request, org):
    package = services.start_package(book_request)
    hardcover = make_book(org, "Hard", format="hardcover")
    services.add_book(package, hardcover)
    ship_url = reverse("shipping:ship", args=[package.pk])
    response = client_coord.post(ship_url, {"shipped_on": "bad"}, follow=True)
    assert response.status_code == 200
    response = client_coord.post(ship_url, {"shipped_on": "2001-01-01"}, follow=True)
    assert b"breaks the facility" in response.content
    client_coord.post(ship_url, {"shipped_on": "2001-01-01", "override_note": "Known risk"})
    package.refresh_from_db()
    assert package.status == "shipped" and package.override_note == "Known risk"

    deliver_url = reverse("shipping:deliver", args=[package.pk])
    response = client_coord.post(deliver_url, {"delivered_on": "nope"}, follow=True)
    assert b"valid delivery date" in response.content
    client_coord.post(deliver_url, {"delivered_on": "2001-01-05"})
    package.refresh_from_db()
    assert package.status == "delivered"
    response = client_coord.post(deliver_url, {"delivered_on": "2001-01-05"}, follow=True)
    assert b"Only shipped packages" in response.content


def test_package_editing_views(client_coord, book_request, book):
    new_url = reverse("shipping:new", args=[book_request.pk])
    response = client_coord.post(new_url)
    package = Package.objects.get()
    assert response["Location"] == package.get_absolute_url()

    item = book_request.items.first()
    client_coord.post(
        reverse("shipping:add_book", args=[package.pk]), {"book": book.pk, "item": item.pk}
    )
    client_coord.post(
        reverse("shipping:add_vendor_item", args=[package.pk]),
        {"title": "Dune", "format": "paperback", "isbn": "0306406152", "item": item.pk},
    )
    response = client_coord.post(
        reverse("shipping:add_vendor_item", args=[package.pk]), {"title": ""}, follow=True
    )
    assert b"Give at least a title" in response.content
    assert package.items.count() == 2
    assert package.items.get(source="vendor").isbn == "9780306406157"

    shelf_item = package.items.get(source="shelf")
    client_coord.post(reverse("shipping:remove_item", args=[package.pk, shelf_item.pk]))
    book.refresh_from_db()
    assert book.quantity == 2

    client_coord.post(reverse("shipping:discard", args=[package.pk]))
    assert not Package.objects.exists()

    book_request.close()
    response = client_coord.post(new_url, follow=True)
    assert b"Reopen the request" in response.content


def test_print_views(client_coord, book_request, book):
    package = services.start_package(book_request)
    services.add_book(package, book)
    slip = client_coord.get(reverse("shipping:slip", args=[package.pk]))
    assert slip.status_code == 200
    assert b"INVOICE / PACKING SLIP" in slip.content  # facility requires an invoice
    assert b"Marcus Reyes #LK-4821" in slip.content
    label = client_coord.get(reverse("shipping:label", args=[package.pk]))
    assert b"MEDIA MAIL" in label.content and b"Testville, PA 00011" in label.content
    batch = client_coord.get(reverse("shipping:print_batch"), {"kind": "slips"})
    assert len(batch.context["pages"]) == 1
    assert client_coord.get(reverse("shipping:print_batch"), {"ids": "999"}).context["pages"] == []


def test_request_actions(client_coord, book_request, book):
    item = book_request.items.first()
    status_url = reverse("correspondence:item_status", args=[book_request.pk, item.pk])
    client_coord.post(status_url)
    item.refresh_from_db()
    assert item.status == RequestedItem.Status.UNAVAILABLE
    client_coord.post(status_url)
    item.refresh_from_db()
    assert item.status == RequestedItem.Status.OPEN

    client_coord.post(
        reverse("correspondence:item_add", args=[book_request.pk]),
        {"description": "Dune", "kind": "title"},
    )
    assert book_request.items.count() == 3
    response = client_coord.post(
        reverse("correspondence:item_add", args=[book_request.pk]), {}, follow=True
    )
    assert b"Describe the book" in response.content

    package = services.start_package(book_request)
    response = client_coord.post(
        reverse("correspondence:request_close", args=[book_request.pk]), follow=True
    )
    assert b"Ship or discard" in response.content
    services.discard_package(package)
    client_coord.post(
        reverse("correspondence:request_close", args=[book_request.pk]), {"reason": "Fulfilled"}
    )
    book_request.refresh_from_db()
    assert book_request.status == "closed" and book_request.close_reason == "Fulfilled"
    client_coord.post(reverse("correspondence:request_reopen", args=[book_request.pk]))
    book_request.refresh_from_db()
    assert book_request.status == "open"


def test_lists_and_people(client_coord, book_request, person, facility):
    for status in ("open", "all", "closed"):
        response = client_coord.get(
            reverse("correspondence:request_list"), {"status": status, "q": "marcus"}
        )
        assert response.status_code == 200
    assert (
        client_coord.get(reverse("correspondence:request_list"), {"q": "LK4821"})
        .context["page"]
        .object_list
    )
    for status in ("packing", "all"):
        assert (
            client_coord.get(reverse("shipping:list"), {"status": status, "q": "x"}).status_code
            == 200
        )
    response = client_coord.get(reverse("correspondence:person_list"), {"q": "marcus"})
    assert list(response.context["page"].object_list) == [person]
    assert client_coord.get(person.get_absolute_url()).status_code == 200
    edit = reverse("correspondence:person_edit", args=[person.pk])
    assert client_coord.get(edit).status_code == 200
    client_coord.post(
        edit,
        {
            "name": "Marcus Q. Reyes",
            "inmate_id": "LK-4821",
            "facility": facility.pk,
            "active": "on",
        },
    )
    person.refresh_from_db()
    assert person.name == "Marcus Q. Reyes"


def test_tenant_isolation(client, other_org, book_request, book):
    outsider = make_user("outsider", other_org)
    client.force_login(outsider)
    package = services.start_package(book_request)
    for url in [
        book_request.get_absolute_url(),
        book_request.person.get_absolute_url(),
        package.get_absolute_url(),
        reverse("shipping:slip", args=[package.pk]),
        reverse("inventory:edit", args=[book.pk]),
    ]:
        assert client.get(url).status_code == 404, url
    assert (
        client.post(
            reverse("shipping:pack_book", args=[book_request.pk]), {"book": book.pk}
        ).status_code
        == 404
    )
    assert b"Marcus" not in client.get(reverse("correspondence:person_list")).content


# ---------------------------------------------------------- facilities ---


def test_public_facility_pages(client, facility, settings):
    assert (
        client.get(
            reverse("facilities:list"), {"q": "test", "state": "PA", "kind": "state-prison"}
        ).status_code
        == 200
    )
    response = client.get(facility.get_absolute_url())
    assert response.status_code == 200 and b"Paperback only" in response.content
    assert "edit/main/dataset/facilities/pa/test-sci.json" in response.context["contribute_url"]
    rules = client.get(reverse("facilities:rules_json", args=[facility.slug])).json()
    assert rules["rules"]["paperback_only"] and rules["rules"]["new_only"]
    assert rules["address"][0] == facility.name
    exported = client.get(reverse("facilities:export", args=[facility.slug]), {"download": "1"})
    assert exported["Content-Disposition"].endswith('test-sci.json"')
    assert json.loads(exported.content)["id"] == "test-sci"

    settings.SHELFPASS = {**settings.SHELFPASS, "PUBLIC_DATA": False}
    assert client.get(reverse("facilities:list")).status_code == 302


def test_rejection_data_views(client, client_coord, book_request, book, today):
    package = services.start_package(book_request)
    item = services.add_book(package, book)
    services.ship(package, shipped_on=today)
    services.log_return(package, "content", today, flagged_item=item)
    overview = client.get(reverse("facilities:rejections"))
    assert overview.status_code == 200 and overview.context["total"] == 1
    data = client.get(reverse("facilities:rejections_json")).json()
    assert data["license"] == "CC-BY-SA-4.0" and data["reports"][0]["reason"] == "content"
    csv_text = client.get(reverse("facilities:rejections_csv")).content.decode()
    assert csv_text.splitlines()[1].startswith("test-sci,")
    assert "Marcus" not in csv_text


def test_create_and_edit_local_facility(client_coord, jurisdiction, facility):
    url = reverse("facilities:create")
    assert client_coord.get(url, {"next": "intake"}).context["next_value"] == "intake"
    data = {
        "name": "New County Jail",
        "kind": "county-jail",
        "jurisdiction": jurisdiction.pk,
        "street": "9 Jail Rd",
        "city": "Newtown",
        "state": "PA",
        "postal_code": "00099",
        "website": "jail.example",
        "paperback_only": "true",
        "new_only": "false",
        "max_books_per_package": "4",
        "max_package_weight_lb": "2.5",
        "banned_content": ["tattoo"],
        "banned_titles": "Book One — Author A\nBook Two",
        "approved_vendors": "Publisher",
        "rule_notes": "Line one\n\nLine two",
        "recipient_format": "{name} ({id})",
        "book_mail_address": "Center\nPO Box 1",
        "source_links": "Policy | https://example.org/policy\nhttps://example.org/two\nA phone call",
        "next": "intake",
    }
    response = client_coord.post(url, data)
    new = Facility.objects.get(name="New County Jail")
    assert response["Location"].endswith(f"?facility={new.pk}")
    assert new.slug == "local-pa-new-county-jail" and new.origin == Origin.LOCAL
    assert new.website == "https://jail.example"
    assert new.rules["banned_titles"] == [
        {"title": "Book One", "author": "Author A"},
        {"title": "Book Two"},
    ]
    assert new.rules["paperback_only"] is True and new.rules["new_only"] is False
    assert new.sources == [
        {"title": "Policy", "url": "https://example.org/policy"},
        {"url": "https://example.org/two"},
        {"title": "A phone call"},
    ]
    assert new.ruleset.invoice_required  # inherited from the jurisdiction

    client_coord.post(url, {**data, "next": ""})
    assert Facility.objects.filter(slug="local-pa-new-county-jail-2").exists()

    edit = reverse("facilities:edit", args=[new.slug])
    form = client_coord.get(edit).context["form"]
    assert form.initial["paperback_only"] == "true"
    assert "Book One — Author A" in form.initial["banned_titles"]
    client_coord.post(edit, {**data, "name": "Renamed Jail", "recipient_format": "{bad}"})
    new.refresh_from_db()
    assert new.name == "New County Jail"  # invalid format rejected
    client_coord.post(edit, {**data, "name": "Renamed Jail"})
    new.refresh_from_db()
    assert new.name == "Renamed Jail" and new.slug == "local-pa-new-county-jail"

    detail = client_coord.get(new.get_absolute_url())
    assert "/new/main/dataset/facilities/pa?" in detail.context["contribute_url"]
    # Dataset facilities can't be edited locally.
    assert client_coord.get(reverse("facilities:edit", args=[facility.slug])).status_code == 302


# ---------------------------------------------------------------- shelf ---


def test_shelf_crud(client_coord, org):
    url = reverse("inventory:create")
    assert client_coord.get(url, {"title": "Dune"}).context["form"].initial["title"] == "Dune"
    data = {
        "title": "Dune",
        "authors": "Frank Herbert",
        "isbn": "0-306-40615-2",
        "format": "paperback",
        "condition": "used",
        "category": "fantasy",
        "quantity": "2",
        "subjects_text": "Science fiction, Desert",
        "content_flags": ["maps-travel"],
    }
    client_coord.post(url, {**data, "add_another": "1"})
    book = Book.objects.get()
    assert book.isbn == "9780306406157" and book.subjects == ["Science fiction", "Desert"]
    assert book.content_flags == ["maps-travel"]
    response = client_coord.post(url, {**data, "isbn": "12345"})
    assert "valid ISBN" in str(response.context["form"].errors)

    edit = reverse("inventory:edit", args=[book.pk])
    assert (
        client_coord.get(edit).context["form"].initial["subjects_text"] == "Science fiction, Desert"
    )
    client_coord.post(edit, {**data, "quantity": "5"})
    book.refresh_from_db()
    assert book.quantity == 5

    adjust = reverse("inventory:adjust", args=[book.pk])
    client_coord.post(adjust, {"delta": "1", "next": "https://evil.example/"})
    book.refresh_from_db()
    assert book.quantity == 6
    response = client_coord.post(adjust, {"delta": "-1"}, HTTP_ACCEPT="application/json")
    assert response.json() == {"quantity": 5}

    for params in (
        {"q": "dune"},
        {"q": "9780306406157", "stock": "all"},
        {"category": "fantasy", "format": "paperback", "condition": "used", "stock": "out"},
    ):
        assert client_coord.get(reverse("inventory:list"), params).status_code == 200

    exported = client_coord.get(reverse("inventory:export")).content.decode()
    assert exported.splitlines()[0].startswith("title,authors,isbn")
    client_coord.post(reverse("inventory:delete", args=[book.pk]))
    assert not Book.objects.exists()


def test_shelf_import(client_coord, org):
    assert client_coord.get(reverse("inventory:import")).status_code == 200
    make_book(
        org, "Dune", authors="Frank Herbert", format="paperback", condition="used", quantity=1
    )
    csv_text = (
        "Title,Authors,ISBN,Format,Condition,Category,Quantity,Location\n"
        "Dune,Frank Herbert,,paperback,used,fantasy,2,A1\n"
        "The Hobbit,Tolkien,0-306-40615-2,Mass-market paperback,New,Fantasy & science fiction,x,B2\n"
        ",,,,,,,\n"
    )
    upload = io.BytesIO(csv_text.encode("utf-8-sig"))
    upload.name = "shelf.csv"
    response = client_coord.post(reverse("inventory:import"), {"file": upload}, follow=True)
    assert b"1 new, 1 restocked, 1 skipped" in response.content
    assert Book.objects.get(title="Dune").quantity == 3
    hobbit = Book.objects.get(title="The Hobbit")
    assert (hobbit.format, hobbit.condition, hobbit.category, hobbit.quantity) == (
        "mass-market",
        "new",
        "fantasy",
        1,
    )

    latin = io.BytesIO("title\nCaf\xe9 Stories\n".encode("latin-1"))
    latin.name = "old.csv"
    client_coord.post(reverse("inventory:import"), {"file": latin})
    assert Book.objects.filter(title="Café Stories").exists()


def test_openlibrary_lookup_view(client_coord, monkeypatch):
    from shelfpass.inventory import openlibrary

    monkeypatch.setattr(
        openlibrary,
        "search",
        lambda q, limit=8: [openlibrary.BookCandidate(title="Dune", cover_id="1")],
    )
    data = client_coord.get(reverse("inventory:lookup"), {"q": "dune"}).json()
    assert data["results"][0]["cover_url"].endswith("/1-M.jpg")


# ----------------------------------------------------------------- team ---


def test_team_management(client_coord, coordinator, volunteer, org):
    assert client_coord.get(reverse("orgs:team")).status_code == 200
    add = reverse("orgs:member_add")
    assert client_coord.get(add).status_code == 200
    response = client_coord.post(
        add, {"username": "newbie", "role": "volunteer", "password": "short"}
    )
    assert "password" in response.context["form"].errors
    client_coord.post(
        add, {"username": "newbie", "role": "volunteer", "password": "a-long-enough-passphrase"}
    )
    newbie = Membership.objects.get(user__username="newbie")
    response = client_coord.post(
        add, {"username": "NEWBIE", "role": "volunteer", "password": "a-long-enough-passphrase"}
    )
    assert "already in this group" in str(response.context["form"].errors)
    make_user("elsewhere")
    response = client_coord.post(
        add, {"username": "elsewhere", "role": "volunteer", "password": "a-long-enough-passphrase"}
    )
    assert "taken" in str(response.context["form"].errors)

    client_coord.post(reverse("orgs:member_role", args=[newbie.pk]), {"role": "coordinator"})
    newbie.refresh_from_db()
    assert newbie.is_coordinator
    me = Membership.objects.get(user=coordinator)
    client_coord.post(reverse("orgs:member_role", args=[newbie.pk]), {"role": "volunteer"})
    response = client_coord.post(
        reverse("orgs:member_role", args=[me.pk]), {"role": "volunteer"}, follow=True
    )
    assert b"at least one coordinator" in response.content

    response = client_coord.post(reverse("orgs:member_remove", args=[me.pk]), follow=True)
    assert b"can&#x27;t remove yourself" in response.content
    client_coord.post(reverse("orgs:member_remove", args=[newbie.pk]))
    assert not Membership.objects.filter(pk=newbie.pk).exists()

    settings_url = reverse("orgs:settings")
    assert client_coord.get(settings_url).status_code == 200
    client_coord.post(
        settings_url,
        {
            "name": "Renamed Group",
            "return_address": "PO Box 5",
            "packing_slip_note": "Thanks",
            "share_rejections": "",
        },
    )
    org.refresh_from_db()
    assert org.name == "Renamed Group" and not org.share_rejections


def test_volunteers_cannot_manage_team(client_vol):
    assert client_vol.get(reverse("orgs:team")).status_code == 200
    assert client_vol.get(reverse("orgs:member_add")).status_code == 403
    assert client_vol.get(reverse("orgs:settings")).status_code == 403


def test_switch_group(client, coordinator, other_org):
    Membership.objects.create(user=coordinator, organization=other_org)
    client.force_login(coordinator)
    response = client.post(
        reverse("orgs:switch"), {"organization": other_org.pk, "next": "/people/"}
    )
    assert response["Location"] == "/people/"
    assert client.session[SESSION_KEY] == other_org.pk
    assert client.get(reverse("core:dashboard")).context["current_org"] == other_org
    response = client.post(
        reverse("orgs:switch"), {"organization": "abc", "next": "https://evil.example"}
    )
    assert response["Location"] == "/"
