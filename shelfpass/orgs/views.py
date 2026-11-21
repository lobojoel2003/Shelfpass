from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from shelfpass.core.utils import redirect_next
from shelfpass.orgs.access import coordinator_required, org_required
from shelfpass.orgs.forms import MemberAddForm, MembershipRoleForm, OrganizationForm
from shelfpass.orgs.middleware import SESSION_KEY
from shelfpass.orgs.models import Membership


@org_required
def team(request):
    members = (
        Membership.objects.filter(organization=request.organization)
        .select_related("user")
        .order_by("role", "user__first_name", "user__username")
    )
    return render(request, "orgs/team.html", {"members": members, "roles": Membership.Role.choices})


@coordinator_required
def member_add(request):
    form = MemberAddForm(request.POST or None, organization=request.organization)
    if request.method == "POST" and form.is_valid():
        membership = form.save()
        messages.success(request, f"Added {membership.user.username} to {request.organization}.")
        return redirect("orgs:team")
    return render(request, "orgs/member_form.html", {"form": form})


@coordinator_required
@require_POST
def member_role(request, pk: int):
    membership = get_object_or_404(Membership, pk=pk, organization=request.organization)
    was_coordinator = membership.is_coordinator  # is_valid() copies the new role onto the instance
    form = MembershipRoleForm(request.POST, instance=membership)
    if form.is_valid():
        demoting_last = (
            was_coordinator
            and form.cleaned_data["role"] != Membership.Role.COORDINATOR
            and not Membership.objects.filter(
                organization=request.organization, role=Membership.Role.COORDINATOR
            )
            .exclude(pk=membership.pk)
            .exists()
        )
        if demoting_last:
            messages.error(request, "A group needs at least one coordinator.")
        else:
            form.save()
            messages.success(
                request,
                f"{membership.user.username} is now a {membership.get_role_display().lower()}.",
            )
    return redirect("orgs:team")


@coordinator_required
@require_POST
def member_remove(request, pk: int):
    membership = get_object_or_404(Membership, pk=pk, organization=request.organization)
    if membership.user_id == request.user.pk:
        messages.error(request, "You can't remove yourself. Ask another coordinator.")
    else:
        membership.delete()
        messages.success(request, f"Removed {membership.user.username} from the group.")
    return redirect("orgs:team")


@coordinator_required
def settings_view(request):
    form = OrganizationForm(request.POST or None, instance=request.organization)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Group settings saved.")
        return redirect("orgs:settings")
    return render(request, "orgs/settings.html", {"form": form})


@login_required
@require_POST
def switch(request):
    org_id = request.POST.get("organization", "")
    membership = (
        Membership.objects.filter(user=request.user, organization_id=int(org_id)).first()
        if org_id.isdigit()
        else None
    )
    if membership:
        request.session[SESSION_KEY] = membership.organization_id
        messages.info(request, f"Switched to {membership.organization}.")
    return redirect_next(request, "core:dashboard")
