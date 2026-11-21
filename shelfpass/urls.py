"""Root URL configuration."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from shelfpass.core import views as core_views

admin.site.site_header = "Shelfpass administration"
admin.site.site_title = "Shelfpass admin"
admin.site.index_title = "Data and settings"

urlpatterns = [
    path("", include("shelfpass.core.urls")),
    path("org/", include("shelfpass.orgs.urls")),
    path("facilities/", include("shelfpass.facilities.urls")),
    path("shelf/", include("shelfpass.inventory.urls")),
    path("", include("shelfpass.correspondence.urls")),
    path("packages/", include("shelfpass.shipping.urls")),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(redirect_authenticated_user=True),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "accounts/password/",
        auth_views.PasswordChangeView.as_view(success_url="/"),
        name="password_change",
    ),
    path("admin/", admin.site.urls),
    path("healthz", core_views.healthz, name="healthz"),
    path("version.json", core_views.version_json, name="version"),
]

handler403 = "shelfpass.core.views.error_403"
handler404 = "shelfpass.core.views.error_404"
handler500 = "shelfpass.core.views.error_500"
