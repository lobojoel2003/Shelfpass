from django.urls import path

from shelfpass.correspondence import views

app_name = "correspondence"

urlpatterns = [
    path("letters/new/", views.intake, name="intake"),
    path("requests/", views.request_list, name="request_list"),
    path("requests/<int:pk>/", views.request_detail, name="request_detail"),
    path("requests/<int:pk>/close/", views.request_close, name="request_close"),
    path("requests/<int:pk>/reopen/", views.request_reopen, name="request_reopen"),
    path("requests/<int:pk>/items/", views.item_add, name="item_add"),
    path("requests/<int:pk>/items/<int:item_pk>/status/", views.item_status, name="item_status"),
    path("people/", views.person_list, name="person_list"),
    path("people/lookup.json", views.person_lookup, name="person_lookup"),
    path("people/<int:pk>/", views.person_detail, name="person_detail"),
    path("people/<int:pk>/edit/", views.person_edit, name="person_edit"),
]
