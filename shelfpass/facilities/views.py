from __future__ import annotations

import csv
from collections import Counter
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from shelfpass.facilities import dataset as ds
from shelfpass.facilities.forms import FacilityForm
from shelfpass.facilities.history import (
    public_reports,
    reason_breakdown,
    rejection_events,
    shipping_stats,
    window_start,
)
from shelfpass.facilities.models import Facility
from shelfpass.facilities.vocab import US_STATES, FacilityKind
from shelfpass.orgs.access import org_required, public_or_org


@public_or_org
def facility_list(request):
    facilities = Facility.objects.select_related("jurisdiction")
    query = request.GET.get("q", "").strip()
    state = request.GET.get("state", "")
    kind = request.GET.get("kind", "")
    show_inactive = request.GET.get("inactive") == "1"
    facilities = facilities.search(query)
    if state:
        facilities = facilities.filter(state=state)
    if kind:
        facilities = facilities.filter(kind=kind)
    if not show_inactive:
        facilities = facilities.active()

    since = window_start()
    events = rejection_events(since=since)
    counts = Counter(e.facility_slug for e in events)

    page = Paginator(facilities.order_by("state", "name"), 40).get_page(request.GET.get("page"))
    for facility in page:
        facility.recent_rejections = counts.get(facility.slug, 0)
    return render(
        request,
        "facilities/facility_list.html",
        {
            "page": page,
            "query": query,
            "state": state,
            "kind": kind,
            "states": US_STATES,
            "kinds": FacilityKind.choices,
            "show_inactive": show_inactive,
            "total": Facility.objects.active().count(),
        },
    )


@public_or_org
def facility_detail(request, slug: str):
    facility = get_object_or_404(Facility.objects.select_related("jurisdiction"), slug=slug)
    since = window_start()
    events = rejection_events(facility, viewer_org=request.organization)
    recent = [e for e in events if e.date >= since.replace(day=1)]
    context = {
        "facility": facility,
        "rules": facility.ruleset,
        "events": events[:25],
        "event_total": len(events),
        "breakdown": reason_breakdown(recent),
        "recent_total": len(recent),
        "stats": shipping_stats(facility, since),
        "window_days": settings.SHELFPASS["REJECTION_WINDOW_DAYS"],
        "dataset_path": facility.dataset_path or ds.facility_dataset_path(facility),
        "contribute_url": _contribute_url(facility),
    }
    if request.organization is not None:
        from shelfpass.shipping.models import Package

        context["our_packages"] = (
            Package.objects.filter(organization=request.organization, facility=facility)
            .select_related("person")
            .order_by("-created_at")[:8]
        )
        context["our_people"] = facility.people.filter(organization=request.organization).count()
    return render(request, "facilities/facility_detail.html", context)


def _contribute_url(facility: Facility) -> str:
    """GitHub link that opens the dataset file for editing, or pre-fills a new one."""
    repo = settings.SHELFPASS["DATASET_REPO_URL"].rstrip("/")
    if facility.is_from_dataset and facility.dataset_path:
        return f"{repo}/edit/main/dataset/{facility.dataset_path}"
    path = ds.facility_dataset_path(facility)
    directory, _, filename = path.rpartition("/")
    query = urlencode({"filename": filename, "value": ds.dumps(ds.facility_to_dataset(facility))})
    return f"{repo}/new/main/dataset/{directory}?{query}"


@org_required
def facility_create(request):
    form = FacilityForm(request.POST or None, initial={"state": request.GET.get("state", "")})
    if request.method == "POST" and form.is_valid():
        facility = form.save()
        messages.success(
            request,
            f"Added {facility.name}. Please share it with other groups by exporting it to the "
            "dataset when you're confident in the rules.",
        )
        next_url = request.POST.get("next")
        if next_url == "intake":
            return redirect(f"{_intake_url()}?facility={facility.pk}")
        return redirect(facility)
    next_value = request.POST.get("next") or request.GET.get("next", "")
    return render(
        request,
        "facilities/facility_form.html",
        {
            "form": form,
            "creating": True,
            "next_value": next_value if next_value == "intake" else "",
        },
    )


def _intake_url() -> str:
    from django.urls import reverse

    return reverse("correspondence:intake")


@org_required
def facility_edit(request, slug: str):
    facility = get_object_or_404(Facility, slug=slug)
    if facility.is_from_dataset:
        messages.info(
            request,
            "This facility comes from the shared dataset. Suggest a correction there so every "
            "group gets it.",
        )
        return redirect(facility)
    form = FacilityForm(request.POST or None, instance=facility)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Facility updated.")
        return redirect(facility)
    return render(request, "facilities/facility_form.html", {"form": form, "facility": facility})


@public_or_org
def facility_rules_json(request, slug: str):
    """Rules summary used by the letter-intake form as soon as a facility is picked."""
    facility = get_object_or_404(Facility.objects.select_related("jurisdiction"), slug=slug)
    rules = facility.ruleset
    events = rejection_events(facility, since=window_start(), viewer_org=request.organization)
    return JsonResponse(
        {
            "id": facility.pk,
            "slug": facility.slug,
            "name": facility.name,
            "url": facility.get_absolute_url(),
            "summary": rules.summary(),
            "badges": [vars(b) for b in rules.badges()],
            "notes": list(rules.notes),
            "recipient_format": rules.recipient_format,
            "address": facility.book_address_lines,
            "is_sample": facility.is_sample,
            "last_verified": facility.last_verified.isoformat() if facility.last_verified else None,
            "rejections": {
                "total": len(events),
                "window_days": settings.SHELFPASS["REJECTION_WINDOW_DAYS"],
                "reasons": [vars(r) for r in reason_breakdown(events)[:4]],
                "recent": [
                    {
                        "date": e.date.isoformat(),
                        "month_only": e.month_only,
                        "reason": e.reason_label,
                        "title": e.title,
                        "format": e.format_label,
                    }
                    for e in events[:3]
                ],
            },
            "rules": rules.as_dict(),
        }
    )


@public_or_org
def facility_export(request, slug: str):
    """The facility as a dataset JSON file, for opening a pull request."""
    facility = get_object_or_404(Facility.objects.select_related("jurisdiction"), slug=slug)
    response = HttpResponse(
        ds.dumps(ds.facility_to_dataset(facility)), content_type="application/json"
    )
    if request.GET.get("download"):
        response["Content-Disposition"] = f'attachment; filename="{facility.slug}.json"'
    return response


@public_or_org
def rejections_overview(request):
    since = window_start()
    events = rejection_events(since=since, viewer_org=request.organization)
    by_facility = Counter((e.facility_slug, e.facility_name) for e in events).most_common(10)
    banned = Counter(
        (e.title, e.authors) for e in events if e.title and e.reason == "content"
    ).most_common(10)
    return render(
        request,
        "facilities/rejections.html",
        {
            "events": events[:30],
            "total": len(events),
            "breakdown": reason_breakdown(events),
            "by_facility": by_facility,
            "banned": banned,
            "window_days": settings.SHELFPASS["REJECTION_WINDOW_DAYS"],
        },
    )


def _public_rejections():
    return public_reports()


@public_or_org
def rejections_json(request):
    payload = {
        "generated": timezone.now().isoformat(timespec="seconds"),
        "license": "CC-BY-SA-4.0",
        "reporter": "",
        "reports": _public_rejections(),
    }
    response = JsonResponse(payload, json_dumps_params={"indent": 2})
    response["Content-Disposition"] = 'inline; filename="shelfpass-rejections.json"'
    return response


@public_or_org
def rejections_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="shelfpass-rejections.csv"'
    writer = csv.writer(response)
    writer.writerow(
        ["facility", "month", "reason", "title", "authors", "isbn", "format", "condition"]
    )
    for report in _public_rejections():
        book = report.get("book", {})
        writer.writerow(
            [
                report["facility"],
                report["month"],
                report["reason"],
                book.get("title", ""),
                book.get("authors", ""),
                book.get("isbn", ""),
                book.get("format", ""),
                book.get("condition", ""),
            ]
        )
    return response
