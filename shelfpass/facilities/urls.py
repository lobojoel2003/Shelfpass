from django.urls import path

from shelfpass.facilities import views

app_name = "facilities"

urlpatterns = [
    path("", views.facility_list, name="list"),
    path("new/", views.facility_create, name="create"),
    path("rejections/", views.rejections_overview, name="rejections"),
    path("data/rejections.json", views.rejections_json, name="rejections_json"),
    path("data/rejections.csv", views.rejections_csv, name="rejections_csv"),
    path("<slug:slug>/", views.facility_detail, name="detail"),
    path("<slug:slug>/edit/", views.facility_edit, name="edit"),
    path("<slug:slug>/rules.json", views.facility_rules_json, name="rules_json"),
    path("<slug:slug>/dataset.json", views.facility_export, name="export"),
]
