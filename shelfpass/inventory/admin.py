from django.contrib import admin

from shelfpass.inventory.models import Book


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "authors",
        "format",
        "condition",
        "category",
        "quantity",
        "organization",
    ]
    list_filter = ["organization", "format", "condition", "category"]
    search_fields = ["title", "authors", "isbn"]
