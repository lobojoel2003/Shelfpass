from django.urls import path

from shelfpass.shipping import views

app_name = "shipping"

urlpatterns = [
    path("", views.package_list, name="list"),
    path("returns/", views.return_list, name="returns"),
    path("print/", views.print_batch, name="print_batch"),
    path("for-request/<int:request_pk>/pack/", views.pack_book, name="pack_book"),
    path("for-request/<int:request_pk>/new/", views.package_new, name="new"),
    path("<int:pk>/", views.package_detail, name="detail"),
    path("<int:pk>/add/", views.add_book, name="add_book"),
    path("<int:pk>/vendor/", views.add_vendor_item, name="add_vendor_item"),
    path("<int:pk>/items/<int:item_pk>/remove/", views.remove_item, name="remove_item"),
    path("<int:pk>/discard/", views.discard, name="discard"),
    path("<int:pk>/ship/", views.ship, name="ship"),
    path("<int:pk>/deliver/", views.deliver, name="deliver"),
    path("<int:pk>/return/", views.log_return, name="log_return"),
    path("<int:pk>/slip/", views.packing_slip, name="slip"),
    path("<int:pk>/label/", views.label, name="label"),
]
