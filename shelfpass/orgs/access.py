"""View decorators that enforce group membership and roles."""

from __future__ import annotations

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import render


def org_required(view):
    """Require a logged-in volunteer who belongs to at least one group."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if request.organization is None:
            return render(request, "orgs/no_group.html", status=403)
        return view(request, *args, **kwargs)

    return wrapper


def coordinator_required(view):
    """Require the coordinator role in the current group."""

    @org_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not (request.membership.is_coordinator or request.user.is_superuser):
            raise PermissionDenied("Only group coordinators can do that.")
        return view(request, *args, **kwargs)

    return wrapper


def public_or_org(view):
    """Allow anonymous access when public data is enabled, otherwise require a group."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        from django.conf import settings

        if settings.SHELFPASS["PUBLIC_DATA"] or request.organization is not None:
            return view(request, *args, **kwargs)
        return org_required(view)(request, *args, **kwargs)

    return wrapper
