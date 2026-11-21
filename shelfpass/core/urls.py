from django.urls import path

from shelfpass.core import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
]
