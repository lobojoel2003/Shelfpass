"""Fill an empty database with a realistic, entirely fictional demo.

Creates two groups, a coordinator login (``demo`` / ``shelfpass-demo``), a
shelf of donated books, readers at the sample facilities, and letters in every
state: waiting, packing, shipped, delivered, returned and closed.
"""

from __future__ import annotations

import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from shelfpass.correspondence.models import BookRequest, Person, RequestedItem
from shelfpass.facilities.dataset import load_dataset, sync_dataset
from shelfpass.facilities.models import Facility
from shelfpass.inventory.models import Book
from shelfpass.orgs.models import Membership, Organization
from shelfpass.shipping import services
from shelfpass.shipping.models import Package

DEMO_PASSWORD = "shelfpass-demo"  # noqa: S105 - documented demo credential

SHELF = [
    # title, authors, format, condition, category, qty, location, flags
    (
        "The Merriam-Webster Dictionary",
        "Merriam-Webster",
        "mass-market",
        "new",
        "reference",
        6,
        "A1",
        [],
    ),
    (
        "Merriam-Webster's Collegiate Dictionary",
        "Merriam-Webster",
        "hardcover",
        "new",
        "reference",
        2,
        "A1",
        [],
    ),
    (
        "Webster's New World Thesaurus",
        "Charlton Laird",
        "paperback",
        "used",
        "reference",
        2,
        "A1",
        [],
    ),
    (
        "Spanish-English Dictionary",
        "Merriam-Webster",
        "mass-market",
        "new",
        "language",
        5,
        "A2",
        [],
    ),
    ("GED Test Prep Plus", "Caren Van Slyke", "paperback", "new", "education", 4, "B1", []),
    (
        "GED Test Prep 2026-2027",
        "Barron's Educational Series",
        "paperback",
        "used",
        "education",
        2,
        "B1",
        [],
    ),
    ("Algebra I For Dummies", "Mary Jane Sterling", "paperback", "used", "education", 1, "B2", []),
    ("The Hobbit", "J.R.R. Tolkien", "paperback", "used", "fantasy", 2, "C1", []),
    ("The Hobbit", "J.R.R. Tolkien", "paperback", "new", "fantasy", 1, "C1", []),
    ("The Fellowship of the Ring", "J.R.R. Tolkien", "mass-market", "used", "fantasy", 1, "C1", []),
    ("A Game of Thrones", "George R. R. Martin", "hardcover", "used", "fantasy", 1, "C2", []),
    ("A Game of Thrones", "George R. R. Martin", "mass-market", "used", "fantasy", 2, "C2", []),
    ("The Name of the Wind", "Patrick Rothfuss", "paperback", "new", "fantasy", 1, "C2", []),
    (
        "Mistborn: The Final Empire",
        "Brandon Sanderson",
        "paperback",
        "used",
        "fantasy",
        3,
        "C3",
        [],
    ),
    ("The Way of Kings", "Brandon Sanderson", "mass-market", "used", "fantasy", 1, "C3", []),
    ("Dune", "Frank Herbert", "paperback", "used", "fantasy", 2, "C4", []),
    (
        "The Autobiography of Malcolm X",
        "Malcolm X; Alex Haley",
        "paperback",
        "used",
        "biography",
        2,
        "D1",
        [],
    ),
    ("Becoming", "Michelle Obama", "hardcover", "new", "biography", 1, "D1", []),
    ("The Count of Monte Cristo", "Alexandre Dumas", "paperback", "used", "fiction", 1, "E1", []),
    (
        "Their Eyes Were Watching God",
        "Zora Neale Hurston",
        "paperback",
        "used",
        "fiction",
        2,
        "E1",
        [],
    ),
    ("The Alchemist", "Paulo Coelho", "paperback", "new", "fiction", 3, "E2", []),
    ("Gone Girl", "Gillian Flynn", "paperback", "used", "mystery", 1, "E3", []),
    ("Man's Search for Meaning", "Viktor E. Frankl", "paperback", "used", "self-help", 2, "F1", []),
    ("The Four Agreements", "Don Miguel Ruiz", "paperback", "used", "self-help", 2, "F1", []),
    ("The Power of Now", "Eckhart Tolle", "paperback", "used", "religion", 1, "F2", []),
    ("You Are Your Own Gym", "Mark Lauren", "paperback", "new", "health", 2, "F3", []),
    (
        "Krav Maga for Beginners",
        "Darren Levine",
        "paperback",
        "used",
        "health",
        1,
        "F3",
        ["martial-arts"],
    ),
    (
        "Road Atlas: United States",
        "Rand McNally",
        "paperback",
        "new",
        "reference",
        1,
        "A3",
        ["maps-travel"],
    ),
    (
        "Drawing on the Right Side of the Brain",
        "Betty Edwards",
        "paperback",
        "used",
        "arts",
        1,
        "G1",
        [],
    ),
    (
        "The Jailhouse Lawyer's Handbook",
        "Center for Constitutional Rights",
        "paperback",
        "new",
        "legal",
        4,
        "G2",
        [],
    ),
    ("The New Jim Crow", "Michelle Alexander", "paperback", "used", "history", 2, "G3", []),
    ("A Brief History of Time", "Stephen Hawking", "paperback", "used", "science", 1, "G4", []),
    ("Rich Dad Poor Dad", "Robert T. Kiyosaki", "paperback", "used", "business", 1, "G5", []),
    ("Milk and Honey", "Rupi Kaur", "paperback", "new", "poetry", 2, "G6", []),
    (
        "Player's Handbook",
        "Wizards RPG Team",
        "hardcover",
        "new",
        "other",
        1,
        "H1",
        ["role-playing-games"],
    ),
]


class Command(BaseCommand):
    help = "Load fictional demo data (two groups, readers, shelf, letters, packages, returns)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true", help="Delete existing demo groups first."
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow running with DEBUG off. The demo login has a published password.",
        )

    def handle(self, *args, reset=False, force=False, **options):
        if not settings.DEBUG and not force:
            raise CommandError(
                "Refusing to create demo accounts with DEBUG off. Pass --force if you're sure."
            )
        with transaction.atomic():
            if reset:
                Organization.objects.filter(
                    slug__in=["riverside-books", "northside-collective"]
                ).delete()
                get_user_model().objects.filter(username__in=["demo", "sam", "northside"]).delete()
            if Organization.objects.filter(slug="riverside-books").exists():
                raise CommandError("Demo data already exists. Use --reset to rebuild it.")
            result = sync_dataset(load_dataset(), include_samples=True)
            self.stdout.write(f"Dataset: {result}")
            self._build()
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo ready. Log in as demo / {DEMO_PASSWORD} (coordinator) or sam / {DEMO_PASSWORD}."
            )
        )

    # ------------------------------------------------------------------

    def _build(self) -> None:
        today = timezone.localdate()
        self.today = today
        User = get_user_model()

        org = Organization.objects.create(
            name="Riverside Books Behind Bars",
            slug="riverside-books",
            return_address="Riverside Books Behind Bars\nPO Box 4410\nRiverside, PA 00010",
            contact_email="hello@riverside-books.example",
            website="https://riverside-books.example",
        )
        other = Organization.objects.create(
            name="Northside Prison Book Collective",
            slug="northside-collective",
            return_address="Northside Prison Book Collective\n88 Library Lane\nNorthside, OH 00020",
        )
        demo = User.objects.create_user(
            "demo",
            "demo@riverside-books.example",
            DEMO_PASSWORD,
            first_name="Alex",
            last_name="Rivera",
        )
        sam = User.objects.create_user(
            "sam", "", DEMO_PASSWORD, first_name="Sam", last_name="Okoro"
        )
        north = User.objects.create_user("northside", "", DEMO_PASSWORD, first_name="Jordan")
        Membership.objects.create(user=demo, organization=org, role=Membership.Role.COORDINATOR)
        Membership.objects.create(user=sam, organization=org, role=Membership.Role.VOLUNTEER)
        Membership.objects.create(user=north, organization=other, role=Membership.Role.COORDINATOR)
        Membership.objects.create(user=demo, organization=other, role=Membership.Role.VOLUNTEER)
        self.user = demo

        for title, authors, fmt, condition, category, qty, location, flags in SHELF:
            Book.objects.create(
                organization=org,
                title=title,
                authors=authors,
                format=fmt,
                condition=condition,
                category=category,
                quantity=qty,
                location=location,
                content_flags=flags,
                weight_oz=14 if fmt == "hardcover" else 9,
            )
        for title, authors, fmt, condition in [
            ("Merriam-Webster's Collegiate Dictionary", "Merriam-Webster", "paperback", "used"),
            ("A Game of Thrones", "George R. R. Martin", "hardcover", "used"),
            ("The Hobbit", "J.R.R. Tolkien", "paperback", "used"),
        ]:
            Book.objects.create(
                organization=other,
                title=title,
                authors=authors,
                format=fmt,
                condition=condition,
                quantity=3,
            )

        f = {x.slug: x for x in Facility.objects.filter(is_sample=True)}
        cedar, riverbend = f["sample-cedar-hollow-sci"], f["sample-riverbend-cf"]
        pine, lakeview, desert = (
            f["sample-pine-ridge-wcc"],
            f["sample-lakeview-county-jail"],
            f["sample-high-desert-fpc"],
        )

        # Marcus: received The Hobbit months ago, now writes again (the screenshot request).
        marcus = self._person(org, "Marcus Reyes", "LK-4821", cedar, "Block C")
        self._shipped(
            org,
            marcus,
            cedar,
            128,
            ["The Hobbit|paperback|new"],
            [("The Hobbit", "title")],
            delivered=118,
        )
        self._letter(
            org,
            marcus,
            cedar,
            3,
            [
                ("GED study guide", "", "topic"),
                ("The Hobbit", "Tolkien", "title"),
                ("Fantasy series like Game of Thrones", "", "topic"),
                ("Spanish dictionary", "", "topic"),
            ],
            notes="Studying for the GED in the spring. Loves long fantasy series. Spanish is his first language.",
        )

        victor = self._person(org, "Victor Huang", "QN-1177", cedar)
        self._letter(
            org,
            victor,
            cedar,
            71,
            [
                ("Rich Dad Poor Dad", "Kiyosaki", "title"),
                ("anything about starting a business", "", "topic"),
            ],
        )

        dana = self._person(org, "Dana Whitfield", "GA-220931", pine, "Dorm 4B")
        self._letter(
            org,
            dana,
            pine,
            41,
            [("Their Eyes Were Watching God", "Hurston", "title"), ("poetry", "", "topic")],
        )

        luz = self._person(org, "Luz Carmona", "LV-0093", lakeview, "Pod 2")
        self._letter(
            org,
            luz,
            lakeview,
            12,
            [
                ("Spanish-English dictionary", "", "topic"),
                ("The Alchemist", "Paulo Coelho", "title"),
            ],
        )

        terrence = self._person(org, "Terrence Ollie", "RB-7710", riverbend)
        req = self._letter(
            org,
            terrence,
            riverbend,
            9,
            [
                ("Dune", "Frank Herbert", "title"),
                ("Man's Search for Meaning", "", "title"),
                ("algebra", "", "topic"),
            ],
        )
        package = services.start_package(req, self.user)
        dune, meaning = req.items.all()[:2]
        services.add_book(package, Book.objects.get(organization=org, title="Dune"), dune)
        services.add_book(
            package, Book.objects.get(organization=org, title="Man's Search for Meaning"), meaning
        )

        andre = self._person(org, "Andre Bishop", "08812-062", desert)
        self._shipped(
            org,
            andre,
            desert,
            10,
            ["The Way of Kings", "Mistborn"],
            [("Brandon Sanderson books", "topic")],
            tracking="9400 1000 0000 0000 0000 01",
        )

        samuel = self._person(org, "Samuel Okafor", "LK-3004", cedar)
        self._shipped(
            org,
            samuel,
            cedar,
            62,
            ["The Merriam-Webster Dictionary"],
            [("dictionary", "topic")],
            delivered=50,
        )

        keisha = self._person(org, "Keisha Monroe", "GA-118402", pine, "Dorm 2A")
        pkg = self._shipped(
            org,
            keisha,
            pine,
            38,
            ["The New Jim Crow"],
            [("The New Jim Crow", "title")],
            override="Sent before the title was on the banned list",
        )
        services.log_return(
            pkg,
            "content",
            today - datetime.timedelta(days=21),
            "Publication denied — on restricted list",
            pkg.items.first(),
            restock=True,
            user=self.user,
        )

        raymond = self._person(org, "Raymond Tull", "LK-5512", cedar)
        pkg = self._shipped(
            org,
            raymond,
            cedar,
            49,
            ["A Game of Thrones|hardcover"],
            [("A Game of Thrones", "title")],
            override="Volunteer missed the hardcover warning",
        )
        services.log_return(
            pkg,
            "hardcover",
            today - datetime.timedelta(days=33),
            "Stamped HARDCOVER NOT PERMITTED",
            pkg.items.first(),
            restock=True,
            user=self.user,
        )

        jolene = self._person(org, "Jolene Pike", "RB-6204", riverbend)
        self._shipped(
            org,
            jolene,
            riverbend,
            95,
            ["Gone Girl", "The Four Agreements"],
            [("mystery novels", "topic"), ("self help", "topic")],
            delivered=84,
            close=True,
        )

        # The other group's returns show up on shared facility pages.
        self.user = north
        p = self._person(other, "Ezra Lyle", "LK-9087", cedar)
        pkg = self._shipped(
            other,
            p,
            cedar,
            26,
            ["Merriam-Webster's Collegiate Dictionary|paperback"],
            [("dictionary", "topic")],
            override="Did not know about the new-only rule",
        )
        services.log_return(
            pkg,
            "used-book",
            today - datetime.timedelta(days=14),
            "",
            pkg.items.first(),
            restock=True,
            user=north,
        )
        p = self._person(other, "Nina Vos", "LV-0410", lakeview)
        pkg = self._shipped(
            other,
            p,
            lakeview,
            30,
            ["The Hobbit"],
            [("The Hobbit", "title")],
            override="Testing whether donated books get through",
        )
        services.log_return(
            pkg,
            "unauthorized-sender",
            today - datetime.timedelta(days=18),
            "UNAUTHORIZED SENDER",
            restock=True,
            user=north,
        )

    # ------------------------------------------------------------------

    def _person(self, org, name, inmate_id, facility, housing=""):
        return Person.objects.create(
            organization=org, name=name, inmate_id=inmate_id, facility=facility, housing=housing
        )

    def _letter(self, org, person, facility, days_ago, items, notes=""):
        req = BookRequest.objects.create(
            organization=org,
            person=person,
            facility=facility,
            received_on=self.today - datetime.timedelta(days=days_ago),
            letter_notes=notes,
            created_by=self.user,
        )
        for position, (description, author, kind) in enumerate(items):
            RequestedItem.objects.create(
                request=req, description=description, author=author, kind=kind, position=position
            )
        return req

    def _shipped(
        self,
        org,
        person,
        facility,
        days_ago,
        titles,
        items,
        delivered=None,
        tracking="",
        override="",
        close=False,
    ):
        req = self._letter(org, person, facility, days_ago + 5, [(d, "", k) for d, k in items])
        package = services.start_package(req, self.user)
        requested = list(req.items.all())
        for index, spec in enumerate(titles):
            title, fmt, condition = ([*spec.split("|"), "", ""])[:3]
            books = Book.objects.filter(organization=org, title__icontains=title, quantity__gt=0)
            if fmt:
                books = books.filter(format=fmt)
            if condition:
                books = books.filter(condition=condition)
            book = books.first()
            if book:
                services.add_book(package, book, requested[min(index, len(requested) - 1)])
        services.ship(
            package,
            shipped_on=self.today - datetime.timedelta(days=days_ago),
            carrier=Package.Carrier.MEDIA_MAIL,
            tracking_number=tracking,
            weight_oz=12 * package.items.count(),
            postage_cents=476,
            override_note=override,
        )
        if delivered is not None:
            services.mark_delivered(package, self.today - datetime.timedelta(days=delivered))
        if close:
            req.refresh_from_db()
            req.close("Fulfilled")
        return package
