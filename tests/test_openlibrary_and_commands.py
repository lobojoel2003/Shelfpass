from __future__ import annotations

import io
import json
import urllib.error

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from shelfpass.correspondence.models import BookRequest
from shelfpass.inventory import openlibrary
from shelfpass.orgs.models import Membership, Organization
from shelfpass.shipping import services
from shelfpass.shipping.models import Package, Return

DOC = {
    "key": "/works/OL27448W",
    "title": "The Lord of the Rings",
    "subtitle": "One volume",
    "author_name": ["J.R.R. Tolkien", "Someone", "Third", "Fourth"],
    "isbn": ["0618640150", "9780618640157", "junk"],
    "publisher": ["Houghton Mifflin"],
    "first_publish_year": 1954,
    "subject": ["Fantasy", "Maps", "Middle Earth"],
    "cover_i": 9255566,
}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_urlopen(monkeypatch):
    calls = []

    def urlopen(request, timeout):
        calls.append((request.full_url, request.headers, timeout))
        return FakeResponse(json.dumps({"docs": [DOC, {"title": ""}]}).encode())

    monkeypatch.setattr(openlibrary.urllib.request, "urlopen", urlopen)
    return calls


def test_search_parses_and_caches(fake_urlopen):
    results = openlibrary.search("lord of the rings")
    assert len(results) == 1
    book = results[0]
    assert book.title == "The Lord of the Rings: One volume"
    assert book.authors == "J.R.R. Tolkien; Someone; Third"
    assert book.isbn == "9780618640157"
    assert book.year == 1954 and book.publisher == "Houghton Mifflin"
    assert book.content_flags == ["maps-travel"]
    assert book.cover_url.endswith("/9255566-M.jpg")
    assert "q=lord+of+the+rings" in fake_urlopen[0][0]
    assert fake_urlopen[0][1]["User-agent"].startswith("Shelfpass/")

    assert openlibrary.search("lord of the rings")[0].title == book.title
    assert len(fake_urlopen) == 1  # second call served from cache


def test_search_by_isbn_prefers_that_isbn(fake_urlopen):
    [book] = openlibrary.search("0-618-64015-0")
    assert "isbn=9780618640157" in fake_urlopen[0][0]
    assert book.isbn == "9780618640157"


def test_search_failures_and_disabled(monkeypatch, settings):
    def broken(request, timeout):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(openlibrary.urllib.request, "urlopen", broken)
    assert openlibrary.search("anything") == []
    assert openlibrary.search("") == []
    settings.SHELFPASS = {**settings.SHELFPASS, "OPENLIBRARY_ENABLED": False}
    assert openlibrary.search("anything") == []


def test_fetch_rejects_other_schemes():
    with pytest.raises(openlibrary.OpenLibraryError):
        openlibrary._fetch_json("file:///etc/passwd")


# ------------------------------------------------------------- commands ---


@pytest.mark.django_db
def test_seed_demo(settings, capsys):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="DEBUG off"):
        call_command("seed_demo")
    call_command("seed_demo", "--force")
    out = capsys.readouterr().out
    assert "Demo ready" in out
    org = Organization.objects.get(slug="riverside-books")
    statuses = set(BookRequest.objects.filter(organization=org).values_list("status", flat=True))
    assert statuses == {"open", "packing", "shipped", "returned", "closed"}
    assert Return.objects.count() == 4
    assert Package.objects.filter(status="packing").count() == 1
    with pytest.raises(CommandError, match="already exists"):
        call_command("seed_demo", "--force")
    call_command("seed_demo", "--force", "--reset")
    assert Organization.objects.filter(slug="riverside-books").count() == 1


@pytest.mark.django_db
def test_bootstrap_group(monkeypatch, capsys):
    with pytest.raises(CommandError, match="at least 10"):
        call_command("bootstrap_group", "--name", "Group", "--username", "coord")
    monkeypatch.setenv("SHELFPASS_BOOTSTRAP_PASSWORD", "a-very-long-password")
    call_command(
        "bootstrap_group",
        "--name",
        "Riverside BTP",
        "--username",
        "coord",
        "--return-address",
        "Riverside BTP\\nPO Box 1",
        "--superuser",
    )
    user = get_user_model().objects.get(username="coord")
    assert user.is_superuser and user.check_password("a-very-long-password")
    membership = Membership.objects.get(user=user)
    assert membership.is_coordinator
    assert membership.organization.return_address == "Riverside BTP\nPO Box 1"
    with pytest.raises(CommandError, match="already exists"):
        call_command("bootstrap_group", "--name", "Riverside BTP", "--username", "coord")


@pytest.mark.django_db
def test_export_rejections(tmp_path, book_request, book, today, capsys):
    package = services.start_package(book_request)
    services.add_book(package, book)
    services.ship(package, shipped_on=today)
    services.log_return(package, "used-book", today)

    call_command("export_rejections", "--reporter", "Test")
    payload = json.loads(capsys.readouterr().out)
    assert payload["reporter"] == "Test" and len(payload["reports"]) == 1

    target = tmp_path / "out.json"
    call_command("export_rejections", "-o", str(target), "--since", "2999-01-01")
    assert json.loads(target.read_text())["reports"] == []
    with pytest.raises(CommandError):
        call_command("export_rejections", "--since", "yesterday")
