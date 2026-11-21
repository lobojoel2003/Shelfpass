"""Attach the volunteer's current group to every request."""

from __future__ import annotations

from shelfpass.orgs.models import Membership

SESSION_KEY = "shelfpass_org_id"


class CurrentOrganizationMiddleware:
    """Sets ``request.membership`` and ``request.organization``.

    A volunteer can belong to several groups; the active one is remembered in
    the session and defaults to the group they joined first.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.membership = None
        request.organization = None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            memberships = list(
                Membership.objects.filter(user=user)
                .select_related("organization")
                .order_by("created_at", "pk")
            )
            request.memberships = memberships
            wanted = request.session.get(SESSION_KEY)
            chosen = next((m for m in memberships if m.organization_id == wanted), None)
            chosen = chosen or (memberships[0] if memberships else None)
            if chosen is not None:
                request.membership = chosen
                request.organization = chosen.organization
        else:
            request.memberships = []
        return self.get_response(request)
