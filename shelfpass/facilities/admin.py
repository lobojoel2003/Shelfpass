from django.contrib import admin

from shelfpass.facilities.models import Facility, Jurisdiction, RejectionReport


@admin.register(Jurisdiction)
class JurisdictionAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "kind", "state", "origin", "is_sample", "last_verified"]
    list_filter = ["kind", "origin", "is_sample"]
    search_fields = ["name", "code"]


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "city", "state", "kind", "origin", "active", "last_verified"]
    list_filter = ["state", "kind", "origin", "active", "is_sample"]
    search_fields = ["name", "slug", "city"]
    autocomplete_fields = ["jurisdiction"]


@admin.register(RejectionReport)
class RejectionReportAdmin(admin.ModelAdmin):
    list_display = ["facility", "month", "reason", "title", "reporter"]
    list_filter = ["reason"]
    search_fields = ["facility__name", "title", "reporter"]
    autocomplete_fields = ["facility"]
