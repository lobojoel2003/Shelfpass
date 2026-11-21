from django.contrib import admin

from shelfpass.shipping.models import Package, PackageItem, Return


class PackageItemInline(admin.TabularInline):
    model = PackageItem
    extra = 0
    raw_id_fields = ["book", "requested_item"]


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ["reference", "person", "facility", "status", "shipped_on", "organization"]
    list_filter = ["organization", "status", "carrier"]
    search_fields = ["person__name", "tracking_number"]
    raw_id_fields = ["request", "person", "facility"]
    inlines = [PackageItemInline]


@admin.register(Return)
class ReturnAdmin(admin.ModelAdmin):
    list_display = ["package", "facility", "reason", "received_on", "organization"]
    list_filter = ["reason", "organization"]
    raw_id_fields = ["package", "facility", "flagged_item"]
