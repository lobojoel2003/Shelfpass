from django.conf import settings
from django.utils.functional import SimpleLazyObject

from shelfpass.version import get_build_info


def _nav_counts(org):
    from shelfpass.correspondence.models import BookRequest
    from shelfpass.shipping.models import Package

    return {
        "waiting": BookRequest.objects.filter(
            organization=org, status=BookRequest.Status.OPEN
        ).count(),
        "packing": Package.objects.filter(organization=org, status=Package.Status.PACKING).count(),
        "returned": BookRequest.objects.filter(
            organization=org, status=BookRequest.Status.RETURNED
        ).count(),
    }


def shelfpass(request):
    membership = getattr(request, "membership", None)
    org = getattr(request, "organization", None)
    return {
        "build": get_build_info(),
        "current_org": org,
        "current_membership": membership,
        "user_memberships": getattr(request, "memberships", []),
        "is_coordinator": bool(
            membership and (membership.is_coordinator or request.user.is_superuser)
        ),
        "nav_counts": SimpleLazyObject(lambda: _nav_counts(org)) if org else {},
        "public_data": settings.SHELFPASS["PUBLIC_DATA"],
        "dataset_repo_url": settings.SHELFPASS["DATASET_REPO_URL"],
    }
