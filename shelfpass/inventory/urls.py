from django.urls import path

from shelfpass.inventory import views

app_name = "inventory"

urlpatterns = [
    path("", views.book_list, name="list"),
    path("new/", views.book_create, name="create"),
    path("import/", views.book_import, name="import"),
    path("export.csv", views.book_export, name="export"),
    path("lookup.json", views.lookup, name="lookup"),
    path("<int:pk>/", views.book_edit, name="edit"),
    path("<int:pk>/delete/", views.book_delete, name="delete"),
    path("<int:pk>/adjust/", views.book_adjust, name="adjust"),
]
