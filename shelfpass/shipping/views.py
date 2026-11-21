from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from shelfpass.core.text import normalize_isbn
from shelfpass.core.utils import to_int
from shelfpass.correspondence.history import find_previous, sent_books
from shelfpass.correspondence.models import BookRequest, RequestedItem
from shelfpass.facilities.history import rejection_events, window_start
from shelfpass.inventory.models import Book
from shelfpass.orgs.access import org_required
from shelfpass.shipping import services
from shelfpass.shipping.forms import DeliverForm, ReturnForm, ShipForm, VendorItemForm
from shelfpass.shipping.models import Package, PackageItem, Return

STATUS_TABS = [
    ("packing", "Packing"),
    ("shipped", "Shipped"),
    ("delivered", "Delivered"),
    ("returned", "Returned"),
    ("lost", "Vanished"),
    ("all", "All"),
]


def _package_for(request, pk: int) -> Package:
    return get_object_or_404(
        Package.objects.select_related("person", "facility__jurisdiction", "request"),
        pk=pk,
        organization=request.organization,
    )


def _errors(request, exc: ValidationError) -> None:
    for message in exc.messages:
        messages.error(request, message)


@org_required
def package_list(request):
    status = request.GET.get("status", "packing")
    packages = Package.objects.filter(organization=request.organization)
    counts = dict(packages.values_list("status").annotate(n=Count("pk")))
    if status != "all":
        packages = packages.filter(status=status)
    if query := request.GET.get("q", "").strip():
        packages = packages.filter(
            Q(person__name__icontains=query) | Q(tracking_number__icontains=query)
        )
    packages = (
        packages.select_related("person", "facility")
        .annotate(item_count=Count("items"))
        .order_by("-shipped_on", "-created_at")
    )
    page = Paginator(packages, 25).get_page(request.GET.get("page"))
    tabs = [
        (key, label, sum(counts.values()) if key == "all" else counts.get(key, 0))
        for key, label in STATUS_TABS
    ]
    return render(
        request,
        "shipping/package_list.html",
        {"page": page, "status": status, "tabs": tabs, "query": request.GET.get("q", "")},
    )


@org_required
@require_POST
def pack_book(request, request_pk: int):
    """Add a shelf book to the request's open package (creating it if needed)."""
    book_request = get_object_or_404(BookRequest, pk=request_pk, organization=request.organization)
    book = get_object_or_404(
        Book, pk=to_int(request.POST.get("book")), organization=request.organization
    )
    item = None
    if item_pk := to_int(request.POST.get("item")):
        item = get_object_or_404(RequestedItem, pk=item_pk, request=book_request)
    try:
        package = services.start_package(book_request, request.user)
        services.add_book(package, book, item)
    except ValidationError as exc:
        _errors(request, exc)
    else:
        messages.success(request, f"Packed “{book.title}” into {package.reference}.")
    anchor = f"#item-{item.pk}" if item else "#package"
    return redirect(book_request.get_absolute_url() + anchor)


@org_required
@require_POST
def package_new(request, request_pk: int):
    book_request = get_object_or_404(BookRequest, pk=request_pk, organization=request.organization)
    try:
        package = services.start_package(book_request, request.user, force_new=True)
    except ValidationError as exc:
        _errors(request, exc)
        return redirect(book_request)
    messages.success(request, f"Started {package.reference}.")
    return redirect(package)


@org_required
def package_detail(request, pk: int):
    package = _package_for(request, pk)
    items = list(package.items.select_related("book", "requested_item"))
    history = sent_books(package.person, exclude_package_id=package.pk)
    duplicates = {item.pk: find_previous(history, item.title, item.isbn) for item in items}

    shelf_results = []
    query = request.GET.get("q", "").strip()
    if query and package.is_editable:
        isbn = normalize_isbn(query)
        shelf_results = (
            Book.objects.in_stock()
            .filter(organization=request.organization)
            .filter(
                Q(title__icontains=query)
                | Q(authors__icontains=query)
                | (Q(isbn=isbn) if isbn else Q(pk__in=[]))
            )
            .order_by("title")[:12]
        )
        rules = package.facility.ruleset
        for book in shelf_results:
            book.allowed = rules.allows_book(book.format, book.condition)
            book.previously_sent = find_previous(history, book.title, book.isbn)

    recent = rejection_events(
        package.facility, since=window_start(), viewer_org=request.organization
    )
    return render(
        request,
        "shipping/package_detail.html",
        {
            "package": package,
            "items": items,
            "duplicates": duplicates,
            "issues": package.check_rules(),
            "rules": package.facility.ruleset,
            "ship_form": ShipForm(initial={"weight_oz": package.estimated_weight_oz()}),
            "deliver_form": DeliverForm(),
            "vendor_form": VendorItemForm(),
            "query": query,
            "shelf_results": shelf_results,
            "open_items": package.request.items.filter(status=RequestedItem.Status.OPEN),
            "recent_rejections": recent[:5],
        },
    )


@org_required
@require_POST
def add_book(request, pk: int):
    package = _package_for(request, pk)
    book = get_object_or_404(
        Book, pk=to_int(request.POST.get("book")), organization=request.organization
    )
    item = None
    if item_pk := to_int(request.POST.get("item")):
        item = get_object_or_404(RequestedItem, pk=item_pk, request=package.request)
    try:
        services.add_book(package, book, item)
    except ValidationError as exc:
        _errors(request, exc)
    else:
        messages.success(request, f"Added “{book.title}”.")
    return redirect(package)


@org_required
@require_POST
def add_vendor_item(request, pk: int):
    package = _package_for(request, pk)
    form = VendorItemForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Give at least a title for the vendor order.")
        return redirect(package)
    item = None
    if item_pk := to_int(request.POST.get("item")):
        item = get_object_or_404(RequestedItem, pk=item_pk, request=package.request)
    data = form.cleaned_data
    try:
        services.add_vendor_item(
            package,
            title=data["title"],
            authors=data.get("authors", ""),
            isbn=normalize_isbn(data.get("isbn", "")),
            format=data["format"],
            requested_item=item,
        )
    except ValidationError as exc:
        _errors(request, exc)
    else:
        messages.success(request, f"Added vendor order “{data['title']}”.")
    return redirect(package)


@org_required
@require_POST
def remove_item(request, pk: int, item_pk: int):
    package = _package_for(request, pk)
    item = get_object_or_404(PackageItem, pk=item_pk, package=package)
    try:
        services.remove_item(item)
    except ValidationError as exc:
        _errors(request, exc)
    else:
        messages.success(request, f"Removed “{item.title}” and put it back on the shelf.")
    return redirect(package)


@org_required
@require_POST
def discard(request, pk: int):
    package = _package_for(request, pk)
    book_request = package.request
    try:
        services.discard_package(package)
    except ValidationError as exc:
        _errors(request, exc)
        return redirect(package)
    messages.success(request, "Package discarded; its books are back on the shelf.")
    return redirect(book_request)


@org_required
@require_POST
def ship(request, pk: int):
    package = _package_for(request, pk)
    form = ShipForm(request.POST)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect(package)
    data = form.cleaned_data
    try:
        services.ship(
            package,
            shipped_on=data["shipped_on"],
            carrier=data.get("carrier", ""),
            tracking_number=data.get("tracking_number", ""),
            weight_oz=data.get("weight_oz"),
            postage_cents=form.postage_cents,
            override_note=data.get("override_note", ""),
        )
    except ValidationError as exc:
        _errors(request, exc)
    else:
        messages.success(request, f"{package.reference} marked as shipped.")
    return redirect(package)


@org_required
@require_POST
def deliver(request, pk: int):
    package = _package_for(request, pk)
    form = DeliverForm(request.POST)
    try:
        if not form.is_valid():
            raise ValidationError("Enter a valid delivery date.")
        services.mark_delivered(package, form.cleaned_data["delivered_on"])
    except ValidationError as exc:
        _errors(request, exc)
    else:
        messages.success(request, f"{package.reference} marked as delivered.")
    return redirect(package)


@org_required
def log_return(request, pk: int):
    package = _package_for(request, pk)
    if hasattr(package, "return_record"):
        messages.info(request, "A return is already logged for this package.")
        return redirect(package)
    initial = {"reason": request.GET.get("reason", "")}
    form = ReturnForm(request.POST or None, package=package, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            services.log_return(
                package,
                reason=data["reason"],
                received_on=data["received_on"],
                detail=data.get("detail", ""),
                flagged_item=data.get("flagged_item"),
                restock=data.get("restock", False),
                user=request.user,
            )
        except ValidationError as exc:
            _errors(request, exc)
        else:
            messages.success(
                request,
                "Return logged. Thank you — every group shipping to this facility can now see it.",
            )
            return redirect(package)
    return render(request, "shipping/return_form.html", {"package": package, "form": form})


@org_required
def return_list(request):
    returns = (
        Return.objects.filter(organization=request.organization)
        .select_related("package__person", "facility", "flagged_item")
        .order_by("-received_on", "-pk")
    )
    page = Paginator(returns, 30).get_page(request.GET.get("page"))
    return render(request, "shipping/return_list.html", {"page": page})


# ---------------------------------------------------------------- printing ---


def _print_context(package: Package) -> dict:
    rules = package.facility.ruleset
    person = package.person
    return {
        "package": package,
        "items": list(package.items.all()),
        "rules": rules,
        "recipient_line": rules.format_recipient(person.name, person.inmate_id, person.housing),
        "address_lines": package.facility.book_address_lines,
        "org": package.organization,
        "today": timezone.localdate(),
    }


@org_required
def packing_slip(request, pk: int):
    package = _package_for(request, pk)
    return render(request, "shipping/print/slips.html", {"pages": [_print_context(package)]})


@org_required
def label(request, pk: int):
    package = _package_for(request, pk)
    return render(request, "shipping/print/labels.html", {"pages": [_print_context(package)]})


@org_required
def print_batch(request):
    """Labels or slips for several packages at once (default: everything being packed)."""
    kind = "slips" if request.GET.get("kind") == "slips" else "labels"
    packages = Package.objects.filter(organization=request.organization).select_related(
        "person", "facility__jurisdiction", "organization"
    )
    ids = [int(i) for i in request.GET.get("ids", "").split(",") if i.strip().isdigit()]
    packages = (
        packages.filter(pk__in=ids) if ids else packages.filter(status=Package.Status.PACKING)
    )
    pages = [_print_context(p) for p in packages.order_by("pk") if p.items.exists()]
    return render(request, f"shipping/print/{kind}.html", {"pages": pages, "batch": True})
