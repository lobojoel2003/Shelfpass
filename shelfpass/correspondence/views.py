from __future__ import annotations

from dataclasses import dataclass, field

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from shelfpass.core.text import normalize_inmate_id
from shelfpass.correspondence.forms import (
    AddItemForm,
    CloseRequestForm,
    IntakeForm,
    PersonForm,
    RequestedItemFormSet,
)
from shelfpass.correspondence.history import SentBook, find_previous, sent_books
from shelfpass.correspondence.models import BookRequest, Person, RequestedItem
from shelfpass.facilities.models import Facility
from shelfpass.inventory.matching import Suggestion, suggest_books
from shelfpass.orgs.access import org_required
from shelfpass.shipping.models import Package
from shelfpass.shipping.services import current_package

STATUS_TABS = [
    ("open", "Waiting"),
    ("packing", "Packing"),
    ("shipped", "Shipped"),
    ("returned", "Returned"),
    ("closed", "Closed"),
    ("all", "All"),
]


# ------------------------------------------------------------------ intake ---


def _resolve_person(org, data) -> tuple[Person, bool]:
    """Find or create the person a letter is from. Returns ``(person, created)``."""
    person = data.get("person_id")
    facility = data["facility"]
    if person is None:
        person = (
            Person.objects.filter(
                organization=org,
                inmate_id_normalized=normalize_inmate_id(data["inmate_id"]),
                facility=facility,
            )
            .order_by("-updated_at")
            .first()
        )
    if person is None:
        person = Person.objects.create(
            organization=org,
            name=data["name"].strip(),
            inmate_id=data["inmate_id"],
            facility=facility,
            housing=data.get("housing", ""),
        )
        return person, True
    person.name = data["name"].strip() or person.name
    person.inmate_id = data["inmate_id"] or person.inmate_id
    person.facility = facility
    person.housing = data.get("housing", "") or person.housing
    person.active = True
    person.save()
    return person, False


@org_required
def intake(request):
    org = request.organization
    initial = {}
    facility_pk = request.GET.get("facility", "")
    if facility_pk.isdigit():
        initial["facility"] = Facility.objects.filter(pk=int(facility_pk)).first()
    if person_pk := request.GET.get("person", ""):
        person = (
            Person.objects.filter(organization=org, pk=int(person_pk)).first()
            if person_pk.isdigit()
            else None
        )
        if person:
            initial.update(
                name=person.name,
                inmate_id=person.inmate_id,
                facility=person.facility,
                housing=person.housing,
                person_id=person.pk,
            )

    form = IntakeForm(request.POST or None, organization=org, initial=initial)
    items = RequestedItemFormSet(request.POST or None, prefix="items")
    if request.method == "POST" and form.is_valid() and items.is_valid():
        with transaction.atomic():
            person, created = _resolve_person(org, form.cleaned_data)
            book_request = BookRequest.objects.create(
                organization=org,
                person=person,
                facility=form.cleaned_data["facility"],
                received_on=form.cleaned_data["received_on"],
                letter_notes=form.cleaned_data.get("letter_notes", ""),
                created_by=request.user,
            )
            for position, item in enumerate(items.items()):
                RequestedItem.objects.create(
                    request=book_request,
                    description=item["description"].strip(),
                    author=item.get("author", "").strip(),
                    kind=item.get("kind") or RequestedItem.Kind.TITLE,
                    position=position,
                )
        verb = "New reader" if created else "Returning reader"
        messages.success(
            request,
            f"Logged {book_request.reference} for {person.name}. {verb}. "
            "Pick books from the shelf below.",
        )
        if "add_another" in request.POST:
            return redirect("correspondence:intake")
        return redirect(book_request)
    return render(request, "correspondence/intake.html", {"form": form, "items": items})


@org_required
def person_lookup(request):
    """People in this group with the typed ID number (used live by the intake form)."""
    normalized = normalize_inmate_id(request.GET.get("inmate_id", ""))
    if len(normalized) < 3:
        return JsonResponse({"matches": []})
    people = (
        Person.objects.filter(organization=request.organization, inmate_id_normalized=normalized)
        .select_related("facility")
        .annotate(
            letters=Count("requests", distinct=True), last_letter=Max("requests__received_on")
        )
        .order_by("-updated_at")[:5]
    )
    matches = []
    for person in people:
        history = sent_books(person)
        matches.append(
            {
                "id": person.pk,
                "name": person.name,
                "inmate_id": person.inmate_id,
                "housing": person.housing,
                "facility_id": person.facility_id,
                "facility": str(person.facility) if person.facility else "",
                "letters": person.letters,
                "last_letter": person.last_letter.isoformat() if person.last_letter else None,
                "active": person.active,
                "url": person.get_absolute_url(),
                "sent": [
                    {
                        "title": s.title,
                        "authors": s.authors,
                        "date": s.shipped_on.isoformat() if s.shipped_on else None,
                    }
                    for s in history[:12]
                ],
                "sent_total": len(history),
            }
        )
    return JsonResponse({"matches": matches})


# ---------------------------------------------------------------- requests ---


@org_required
def request_list(request):
    status = request.GET.get("status", "open")
    query = request.GET.get("q", "").strip()
    qs = BookRequest.objects.filter(organization=request.organization).select_related(
        "person", "facility"
    )
    counts = dict(qs.values_list("status").annotate(n=Count("pk")))
    if status != "all":
        qs = qs.filter(status=status)
    if query:
        qs = qs.filter(
            Q(person__name__icontains=query)
            | Q(person__inmate_id_normalized=normalize_inmate_id(query))
            | Q(items__description__icontains=query)
        ).distinct()
    qs = qs.annotate(item_count=Count("items", distinct=True))
    qs = (
        qs.order_by("received_on", "pk") if status == "open" else qs.order_by("-received_on", "-pk")
    )
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    tabs = [
        (key, label, sum(counts.values()) if key == "all" else counts.get(key, 0))
        for key, label in STATUS_TABS
    ]
    return render(
        request,
        "correspondence/request_list.html",
        {"page": page, "status": status, "query": query, "tabs": tabs},
    )


@dataclass
class ItemRow:
    item: RequestedItem
    suggestions: list[Suggestion] = field(default_factory=list)
    previously_sent: SentBook | None = None
    packed_in: list = field(default_factory=list)


def _request_for(request, pk: int) -> BookRequest:
    return get_object_or_404(
        BookRequest.objects.select_related("person__facility", "facility__jurisdiction"),
        pk=pk,
        organization=request.organization,
    )


@org_required
def request_detail(request, pk: int):
    book_request = _request_for(request, pk)
    person = book_request.person
    facility = person.facility or book_request.facility
    rules = facility.ruleset
    history = sent_books(person)
    packages = list(
        book_request.packages.prefetch_related("items").select_related("facility", "return_record")
    )
    open_package = next((p for p in packages if p.status == Package.Status.PACKING), None)
    in_open_package = {i.book_id for i in open_package.items.all()} if open_package else set()

    rows = []
    for item in book_request.items.prefetch_related("package_items__package"):
        row = ItemRow(item=item)
        row.packed_in = [pi.package for pi in item.package_items.all()]
        row.previously_sent = (
            find_previous(
                [s for s in history if s.package_id not in {p.pk for p in packages}],
                item.description,
            )
            if item.kind == RequestedItem.Kind.TITLE
            else None
        )
        if item.status == RequestedItem.Status.OPEN:
            row.suggestions = suggest_books(
                book_request.organization,
                item.description,
                item.author,
                rules,
                exclude_ids=in_open_package,
            )
            for suggestion in row.suggestions:
                suggestion.previously_sent = find_previous(
                    history, suggestion.book.title, suggestion.book.isbn
                )
        rows.append(row)

    other_requests = (
        person.requests.exclude(pk=book_request.pk)
        .annotate(item_count=Count("items"))
        .order_by("-received_on")[:5]
    )
    issues = open_package.check_rules() if open_package else []
    moved = person.facility_id and person.facility_id != book_request.facility_id
    return render(
        request,
        "correspondence/request_detail.html",
        {
            "req": book_request,
            "person": person,
            "facility": facility,
            "moved": moved,
            "rules": rules,
            "recipient_line": rules.format_recipient(person.name, person.inmate_id, person.housing),
            "rows": rows,
            "packages": packages,
            "open_package": open_package,
            "issues": issues,
            "history": history[:10],
            "history_total": len(history),
            "other_requests": other_requests,
            "add_item_form": AddItemForm(),
            "close_form": CloseRequestForm(),
        },
    )


@org_required
@require_POST
def request_close(request, pk: int):
    book_request = _request_for(request, pk)
    form = CloseRequestForm(request.POST)
    reason = form.cleaned_data["reason"] if form.is_valid() else ""
    if current_package(book_request):
        messages.error(request, "Ship or discard the package that's being packed first.")
        return redirect(book_request)
    book_request.close(reason or "Closed")
    messages.success(request, f"Closed {book_request.reference}.")
    return redirect("correspondence:request_list")


@org_required
@require_POST
def request_reopen(request, pk: int):
    book_request = _request_for(request, pk)
    book_request.reopen()
    messages.success(request, f"Reopened {book_request.reference}.")
    return redirect(book_request)


@org_required
@require_POST
def item_add(request, pk: int):
    book_request = _request_for(request, pk)
    form = AddItemForm(request.POST)
    if form.is_valid():
        RequestedItem.objects.create(
            request=book_request,
            position=book_request.items.count(),
            **form.cleaned_data,
        )
        messages.success(request, "Added to the request.")
    else:
        messages.error(request, "Describe the book or topic to add.")
    return redirect(book_request)


@org_required
@require_POST
def item_status(request, pk: int, item_pk: int):
    book_request = _request_for(request, pk)
    item = get_object_or_404(RequestedItem, pk=item_pk, request=book_request)
    if item.status == RequestedItem.Status.OPEN:
        item.status = RequestedItem.Status.UNAVAILABLE
    elif item.status == RequestedItem.Status.UNAVAILABLE:
        item.status = RequestedItem.Status.OPEN
    item.save(update_fields=["status"])
    return redirect(f"{book_request.get_absolute_url()}#item-{item.pk}")


# ------------------------------------------------------------------ people ---


@org_required
def person_list(request):
    query = request.GET.get("q", "").strip()
    people = Person.objects.filter(organization=request.organization).select_related("facility")
    if query:
        people = people.filter(
            Q(name__icontains=query) | Q(inmate_id_normalized=normalize_inmate_id(query))
        )
    people = people.annotate(
        letters=Count("requests", distinct=True),
        last_letter=Max("requests__received_on"),
        packages_sent=Count(
            "packages",
            filter=Q(packages__status__in=[Package.Status.SHIPPED, Package.Status.DELIVERED]),
            distinct=True,
        ),
    ).order_by("name")
    page = Paginator(people, 30).get_page(request.GET.get("page"))
    return render(request, "correspondence/person_list.html", {"page": page, "query": query})


@org_required
def person_detail(request, pk: int):
    person = get_object_or_404(
        Person.objects.select_related("facility__jurisdiction"),
        pk=pk,
        organization=request.organization,
    )
    requests = person.requests.select_related("facility").annotate(item_count=Count("items"))
    packages = person.packages.select_related("facility", "return_record").prefetch_related("items")
    return render(
        request,
        "correspondence/person_detail.html",
        {
            "person": person,
            "requests": requests,
            "packages": packages,
            "history": sent_books(person),
        },
    )


@org_required
def person_edit(request, pk: int):
    person = get_object_or_404(Person, pk=pk, organization=request.organization)
    form = PersonForm(request.POST or None, instance=person)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Saved.")
        return redirect(person)
    return render(request, "correspondence/person_form.html", {"form": form, "person": person})
