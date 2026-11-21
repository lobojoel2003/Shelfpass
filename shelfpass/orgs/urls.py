from django.urls import path

from shelfpass.orgs import views

app_name = "orgs"

urlpatterns = [
    path("team/", views.team, name="team"),
    path("team/add/", views.member_add, name="member_add"),
    path("team/<int:pk>/role/", views.member_role, name="member_role"),
    path("team/<int:pk>/remove/", views.member_remove, name="member_remove"),
    path("settings/", views.settings_view, name="settings"),
    path("switch/", views.switch, name="switch"),
]
