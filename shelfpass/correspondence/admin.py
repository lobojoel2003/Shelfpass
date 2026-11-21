from django.contrib import admin

from shelfpass.correspondence.models import BookRequest, Person, RequestedItem


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ["name", "inmate_id", "facility", "organization", "active"]
    list_filter = ["organization", "active"]
    search_fields = ["name", "inmate_id"]
    autocomplete_fields = ["facility"]


class RequestedItemInline(admin.TabularInline):
    model = RequestedItem
    extra = 0


@admin.register(BookRequest)
class BookRequestAdmin(admin.ModelAdmin):
    list_display = ["reference", "person", "facility", "received_on", "status", "organization"]
    list_filter = ["organization", "status"]
    search_fields = ["person__name", "person__inmate_id"]
    autocomplete_fields = ["person", "facility"]
    inlines = [RequestedItemInline]
