from __future__ import annotations

import csv
import io

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from shelfpass.core.text import normalize_isbn
from shelfpass.core.utils import redirect_next
from shelfpass.facilities.vocab import BookCondition, BookFormat
from shelfpass.inventory import openlibrary
from shelfpass.inventory.forms import BookForm, ImportForm
from shelfpass.inventory.models import Book, Category
from shelfpass.orgs.access import org_required

CSV_COLUMNS = [
    "title",
    "authors",
    "isbn",
    "format",
    "condition",
    "category",
    "quantity",
    "location",
]


def _books(request):
    return Book.objects.filter(organization=request.organization)


@org_required
def book_list(request):
    books = _books(request)
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")
    fmt = request.GET.get("format", "")
    condition = request.GET.get("condition", "")
    stock = request.GET.get("stock", "in")
    if query:
        isbn = normalize_isbn(query)
        books = books.filter(
            Q(title__icontains=query)
            | Q(authors__icontains=query)
            | Q(location__iexact=query)
            | (Q(isbn=isbn) if isbn else Q(pk__in=[]))
        )
    if category:
        books = books.filter(category=category)
    if fmt:
        books = books.filter(format=fmt)
    if condition:
        books = books.filter(condition=condition)
    if stock == "in":
        books = books.in_stock()
    elif stock == "out":
        books = books.filter(quantity=0)
    totals = _books(request).aggregate(copies=Sum("quantity"))
    page = Paginator(books.order_by("title"), 30).get_page(request.GET.get("page"))
    return render(
        request,
        "inventory/book_list.html",
        {
            "page": page,
            "query": query,
            "category": category,
            "format": fmt,
            "condition": condition,
            "stock": stock,
            "categories": Category.choices,
            "formats": BookFormat.choices,
            "conditions": BookCondition.choices,
            "copies": totals["copies"] or 0,
        },
    )


@org_required
def book_create(request):
    initial = {k: request.GET[k] for k in ("title", "authors", "isbn") if k in request.GET}
    form = BookForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        book = form.save(commit=False)
        book.organization = request.organization
        book.save()
        messages.success(
            request,
            f"Shelved “{book.title}” ({book.quantity} cop{'y' if book.quantity == 1 else 'ies'}).",
        )
        if "add_another" in request.POST:
            return redirect("inventory:create")
        return redirect("inventory:list")
    return render(request, "inventory/book_form.html", {"form": form, "creating": True})


@org_required
def book_edit(request, pk: int):
    book = get_object_or_404(_books(request), pk=pk)
    form = BookForm(request.POST or None, instance=book)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Book updated.")
        return redirect("inventory:list")
    return render(request, "inventory/book_form.html", {"form": form, "book": book})


@org_required
@require_POST
def book_delete(request, pk: int):
    book = get_object_or_404(_books(request), pk=pk)
    title = book.title
    book.delete()
    messages.success(request, f"Removed “{title}” from the shelf.")
    return redirect("inventory:list")


@org_required
@require_POST
def book_adjust(request, pk: int):
    book = get_object_or_404(_books(request), pk=pk)
    delta = 1 if request.POST.get("delta") == "1" else -1
    book.quantity = max(0, book.quantity + delta)
    book.save(update_fields=["quantity", "updated_at"])
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"quantity": book.quantity})
    return redirect_next(request, "inventory:list")


@org_required
def lookup(request):
    """Open Library search proxy for the add-book and intake forms."""
    query = request.GET.get("q", "")
    results = openlibrary.search(query, limit=8)
    return JsonResponse({"query": query, "results": [r.as_dict() for r in results]})


def _choice(value: str, choices, default: str) -> str:
    value = (value or "").strip().lower()
    by_label = {label.lower(): code for code, label in choices}
    if value in dict(choices):
        return value
    return by_label.get(value, default)


@org_required
def book_import(request):
    form = ImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        raw = form.cleaned_data["file"].read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        reader = csv.DictReader(io.StringIO(text))
        created = updated = skipped = 0
        for row in reader:
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            title = row.get("title", "")
            if not title:
                skipped += 1
                continue
            try:
                quantity = max(0, int(row.get("quantity") or 1))
            except ValueError:
                quantity = 1
            values = {
                "authors": row.get("authors") or row.get("author", ""),
                "isbn": normalize_isbn(row.get("isbn", "")),
                "format": _choice(row.get("format", ""), BookFormat.choices, BookFormat.PAPERBACK),
                "condition": _choice(
                    row.get("condition", ""), BookCondition.choices, BookCondition.USED
                ),
                "category": _choice(row.get("category", ""), Category.choices, Category.OTHER),
                "location": row.get("location", "")[:60],
            }
            existing = (
                _books(request)
                .filter(
                    title__iexact=title,
                    authors__iexact=values["authors"],
                    format=values["format"],
                    condition=values["condition"],
                )
                .first()
            )
            if existing:
                existing.quantity += quantity
                existing.save(update_fields=["quantity", "updated_at"])
                updated += 1
            else:
                Book.objects.create(
                    organization=request.organization,
                    title=title[:300],
                    quantity=quantity,
                    **values,
                )
                created += 1
        messages.success(
            request, f"Import finished: {created} new, {updated} restocked, {skipped} skipped."
        )
        return redirect("inventory:list")
    return render(request, "inventory/import.html", {"form": form, "columns": CSV_COLUMNS})


@org_required
def book_export(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="shelf.csv"'
    writer = csv.writer(response)
    writer.writerow(CSV_COLUMNS)
    for book in _books(request).order_by("title"):
        writer.writerow([getattr(book, column) for column in CSV_COLUMNS])
    return response
