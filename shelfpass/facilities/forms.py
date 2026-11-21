"""Forms for facilities added on this instance (and their mail rules)."""

from __future__ import annotations

from django import forms
from django.utils.text import slugify

from shelfpass.facilities.models import Facility, Jurisdiction, Origin
from shelfpass.facilities.vocab import ContentCategory

TRI_STATE = [("", "Unknown / inherit"), ("true", "Yes"), ("false", "No")]
BOOL_RULES = {
    "books_accepted": "Accepts book packages",
    "paperback_only": "Paperback only",
    "new_only": "New books only (no used)",
    "vendor_only": "Must ship from an approved vendor",
    "hardcover_vendor_only": "Hardcovers only from publisher / bookstore",
    "invoice_required": "Invoice or receipt required",
}


def _lines(value: str) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


class FacilityForm(forms.ModelForm):
    """Edits the model fields plus the ``rules`` JSON, field by field."""

    website = forms.URLField(required=False, assume_scheme="https")

    approved_vendors = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 2}), help_text="One per line."
    )
    max_books_per_package = forms.IntegerField(required=False, min_value=1, max_value=100)
    max_package_weight_lb = forms.DecimalField(
        required=False, min_value=0, max_digits=5, decimal_places=1, label="Max package weight (lb)"
    )
    banned_content = forms.MultipleChoiceField(
        required=False, choices=ContentCategory.choices, widget=forms.CheckboxSelectMultiple
    )
    banned_titles = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One per line, as “Title — Author”.",
    )
    rule_notes = forms.CharField(
        label="Rule notes",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Other rules, one per line (e.g. “No stickers or bookstore labels”).",
    )
    recipient_format = forms.CharField(
        required=False,
        help_text="How to address the person. Use {name}, {id} and {housing}. Default: {name} #{id}",
    )
    book_mail_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Central book-processing address",
        help_text="Only if books must go somewhere other than the facility. One line per row.",
    )
    source_links = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Sources",
        help_text="Where these rules come from, one per line: “Title | https://…”.",
    )

    class Meta:
        model = Facility
        fields = [
            "name",
            "kind",
            "jurisdiction",
            "street",
            "city",
            "state",
            "postal_code",
            "phone",
            "website",
            "notes",
            "last_verified",
        ]
        widgets = {
            "street": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "last_verified": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["jurisdiction"].queryset = Jurisdiction.objects.order_by("name")
        for key, label in BOOL_RULES.items():
            self.fields[key] = forms.TypedChoiceField(
                label=label,
                choices=TRI_STATE,
                required=False,
                coerce=lambda v: {"true": True, "false": False}.get(v),
                empty_value=None,
            )
        rules = dict(self.instance.rules or {}) if self.instance.pk else {}
        for key in BOOL_RULES:
            if key in rules:
                self.initial[key] = "true" if rules[key] else "false"
        self.initial.setdefault("approved_vendors", "\n".join(rules.get("approved_vendors", [])))
        self.initial.setdefault("max_books_per_package", rules.get("max_books_per_package"))
        self.initial.setdefault("max_package_weight_lb", rules.get("max_package_weight_lb"))
        self.initial.setdefault("banned_content", rules.get("banned_content", []))
        self.initial.setdefault(
            "banned_titles",
            "\n".join(
                " — ".join(p for p in (t.get("title", ""), t.get("author", "")) if p)
                if isinstance(t, dict)
                else str(t)
                for t in rules.get("banned_titles", [])
            ),
        )
        self.initial.setdefault("rule_notes", "\n".join(rules.get("notes", [])))
        self.initial.setdefault("recipient_format", rules.get("recipient_format", ""))
        self.initial.setdefault("book_mail_address", "\n".join(rules.get("book_mail_address", [])))
        if self.instance.pk:
            self.initial.setdefault(
                "source_links",
                "\n".join(
                    " | ".join(p for p in (s.get("title", ""), s.get("url", "")) if p)
                    for s in self.instance.sources or []
                ),
            )

    rule_field_names = (
        *BOOL_RULES,
        "approved_vendors",
        "max_books_per_package",
        "max_package_weight_lb",
        "banned_content",
        "banned_titles",
        "rule_notes",
        "recipient_format",
        "book_mail_address",
    )

    def clean_recipient_format(self) -> str:
        fmt = self.cleaned_data.get("recipient_format", "").strip()
        if fmt:
            try:
                fmt.format(name="N", id="1", housing="H")
            except (KeyError, IndexError, ValueError) as exc:
                raise forms.ValidationError(
                    "Only {name}, {id} and {housing} placeholders are allowed."
                ) from exc
        return fmt

    def build_rules(self) -> dict:
        data = self.cleaned_data
        rules: dict[str, object] = {}
        for key in BOOL_RULES:
            if data.get(key) is not None:
                rules[key] = data[key]
        if vendors := _lines(data.get("approved_vendors", "")):
            rules["approved_vendors"] = vendors
        if data.get("max_books_per_package"):
            rules["max_books_per_package"] = data["max_books_per_package"]
        if data.get("max_package_weight_lb"):
            rules["max_package_weight_lb"] = float(data["max_package_weight_lb"])
        if data.get("banned_content"):
            rules["banned_content"] = list(data["banned_content"])
        titles = []
        for line in _lines(data.get("banned_titles", "")):
            title, _, author = (
                part.strip() for part in line.replace(" - ", " — ").partition(" — ")
            )
            titles.append({"title": title, "author": author} if author else {"title": title})
        if titles:
            rules["banned_titles"] = titles
        if notes := _lines(data.get("rule_notes", "")):
            rules["notes"] = notes
        if data.get("recipient_format"):
            rules["recipient_format"] = data["recipient_format"]
        if address := _lines(data.get("book_mail_address", "")):
            rules["book_mail_address"] = address
        return rules

    def build_sources(self) -> list[dict]:
        sources = []
        for line in _lines(self.cleaned_data.get("source_links", "")):
            title, sep, url = (p.strip() for p in line.rpartition("|"))
            if not sep:
                title, url = "", line
            entry = {"url": url} if url.startswith(("http://", "https://")) else {"title": line}
            if title and "url" in entry:
                entry = {"title": title, **entry}
            sources.append(entry)
        return sources

    def save(self, commit: bool = True) -> Facility:
        facility = super().save(commit=False)
        facility.rules = self.build_rules()
        facility.sources = self.build_sources()
        if not facility.pk:
            facility.origin = Origin.LOCAL
            base = slugify(f"local-{facility.state}-{facility.name}")[:110] or "local-facility"
            slug, n = base, 2
            while Facility.objects.filter(slug=slug).exists():
                slug, n = f"{base}-{n}", n + 1
            facility.slug = slug
        if commit:
            facility.save()
        return facility
