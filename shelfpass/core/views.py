from __future__ import annotations

import datetime

from django.db import connection
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from shelfpass.correspondence.models import BookRequest
from shelfpass.facilities.history import rejection_events
from shelfpass.facilities.models import Facility
from shelfpass.inventory.models import Book
from shelfpass.orgs.access import org_required
from shelfpass.shipping.models import Package, Return
from shelfpass.version import get_build_info


@org_required
def dashboard(request):
    org = request.organization
    today = timezone.localdate()
    month_start = today.replace(day=1)
    year_ago = today - datetime.timedelta(days=365)

    requests = BookRequest.objects.filter(organization=org)
    packages = Package.objects.filter(organization=org)

    waiting = (
        requests.filter(status=BookRequest.Status.OPEN)
        .select_related("person", "facility__jurisdiction")
        .annotate(item_count=Count("items"))
        .order_by("received_on", "pk")
    )
    shipped_year = packages.filter(shipped_on__gte=year_ago)
    returned_year = Return.objects.filter(organization=org, received_on__gte=year_ago).count()
    shipped_count = shipped_year.count()

    recent_facilities = Facility.objects.filter(
        Q(packages__organization=org, packages__created_at__date__gte=year_ago)
        | Q(book_requests__organization=org, book_requests__status=BookRequest.Status.OPEN)
    ).distinct()
    network_returns = []
    for facility in recent_facilities[:50]:
        network_returns.extend(
            rejection_events(facility, since=today - datetime.timedelta(days=90), viewer_org=org)
        )
    network_returns.sort(key=lambda e: e.date, reverse=True)

    shelf = Book.objects.filter(organization=org).aggregate(
        titles=Count("pk", filter=Q(quantity__gt=0)), copies=Sum("quantity")
    )

    context = {
        "stats": {
            "waiting": waiting.count(),
            "packing": packages.filter(status=Package.Status.PACKING).count(),
            "shipped_month": packages.filter(shipped_on__gte=month_start).count(),
            "returned_attention": requests.filter(status=BookRequest.Status.RETURNED).count(),
            "return_rate": round(100 * returned_year / shipped_count) if shipped_count else 0,
            "shipped_year": shipped_count,
            "shelf_titles": shelf["titles"] or 0,
            "shelf_copies": shelf["copies"] or 0,
        },
        "waiting": waiting[:6],
        "packing": packages.filter(status=Package.Status.PACKING)
        .select_related("person", "facility")
        .annotate(item_count=Count("items"))[:6],
        "needs_attention": requests.filter(status=BookRequest.Status.RETURNED).select_related(
            "person", "facility"
        )[:5],
        "network_returns": network_returns[:6],
        "today": today,
    }
    return render(request, "core/dashboard.html", context)


@never_cache
def healthz(request):
    """Liveness/readiness probe used by Docker, CI smoke tests and load balancers."""
    build = get_build_info()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        database = "ok"
    except Exception:
        database = "unavailable"
    status = 200 if database == "ok" else 503
    return JsonResponse(
        {"status": "ok" if status == 200 else "degraded", "database": database, **build.as_dict()},
        status=status,
    )


def version_json(request):
    return JsonResponse(get_build_info().as_dict())


def error_403(request, exception=None):
    return render(request, "errors/403.html", {"message": str(exception or "")}, status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)
