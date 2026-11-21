from __future__ import annotations

from django import forms

from shelfpass.core.text import normalize_isbn
from shelfpass.facilities.vocab import ContentCategory
from shelfpass.inventory.models import Book


class BookForm(forms.ModelForm):
    content_flags = forms.MultipleChoiceField(
        required=False,
        choices=ContentCategory.choices,
        widget=forms.CheckboxSelectMultiple,
        label="Content some facilities restrict",
    )
    subjects_text = forms.CharField(
        required=False, label="Subjects", help_text="Comma-separated (filled in by Open Library)."
    )

    class Meta:
        model = Book
        fields = [
            "title",
            "authors",
            "isbn",
            "publisher",
            "year",
            "format",
            "condition",
            "category",
            "quantity",
            "location",
            "weight_oz",
            "notes",
            "openlibrary_key",
            "cover_id",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
            "openlibrary_key": forms.HiddenInput(),
            "cover_id": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial.setdefault("subjects_text", ", ".join(self.instance.subjects or []))

    def clean_isbn(self) -> str:
        raw = self.cleaned_data.get("isbn", "").strip()
        isbn = normalize_isbn(raw)
        if raw and not isbn:
            raise forms.ValidationError("That doesn't look like a valid ISBN-10 or ISBN-13.")
        return isbn

    def save(self, commit: bool = True) -> Book:
        book = super().save(commit=False)
        book.subjects = [
            s.strip() for s in self.cleaned_data.get("subjects_text", "").split(",") if s.strip()
        ][:20]
        book.content_flags = list(self.cleaned_data.get("content_flags", []))
        if commit:
            book.save()
        return book


class ImportForm(forms.Form):
    file = forms.FileField(
        label="CSV file",
        help_text=(
            "Columns: title, authors, isbn, format, condition, category, quantity, location. "
            "Only title is required."
        ),
    )

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Please upload a file smaller than 5 MB.")
        return upload
