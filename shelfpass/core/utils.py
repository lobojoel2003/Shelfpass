from __future__ import annotations

from django.shortcuts import redirect, resolve_url
from django.utils.http import url_has_allowed_host_and_scheme


def safe_next(request, default: str, *args) -> str:
    """The ``next`` parameter if it points at this site, otherwise ``default``."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return resolve_url(default, *args)


def redirect_next(request, default: str, *args):
    return redirect(safe_next(request, default, *args))


def to_int(value) -> int:
    """Parse a primary key from user input; 0 (never a valid pk) when it isn't one."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0
