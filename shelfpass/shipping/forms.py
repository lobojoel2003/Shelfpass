from __future__ import annotations

from decimal import Decimal

from django import forms
from django.utils import timezone

from shelfpass.facilities.vocab import BookFormat, RejectionReason
from shelfpass.shipping.models import Package, PackageItem

DATE = forms.DateInput(attrs={"type": "date"})


def not_future(value):
    if value and value > timezone.localdate():
        raise forms.ValidationError("That date is in the future.")
    return value


class ShipForm(forms.Form):
    shipped_on = forms.DateField(initial=timezone.localdate, widget=DATE, validators=[not_future])
    carrier = forms.ChoiceField(
        choices=[("", "—"), *Package.Carrier.choices],
        required=False,
        initial=Package.Carrier.MEDIA_MAIL,
    )
    tracking_number = forms.CharField(max_length=60, required=False)
    weight_oz = forms.IntegerField(required=False, min_value=1, label="Weight (oz)")
    postage = forms.DecimalField(
        required=False, min_value=Decimal("0"), max_digits=7, decimal_places=2, label="Postage ($)"
    )
    override_note = forms.CharField(
        max_length=300,
        required=False,
        label="Ship anyway because…",
        help_text="Required when the package breaks a facility rule.",
    )

    @property
    def postage_cents(self) -> int | None:
        value = self.cleaned_data.get("postage")
        return int(value * 100) if value is not None else None


class DeliverForm(forms.Form):
    delivered_on = forms.DateField(initial=timezone.localdate, widget=DATE, validators=[not_future])


class ReturnForm(forms.Form):
    reason = forms.ChoiceField(choices=RejectionReason.choices)
    received_on = forms.DateField(
        initial=timezone.localdate, widget=DATE, validators=[not_future], label="Came back on"
    )
    detail = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="What the slip or stamp said",
        help_text="Word for word if you can. Visible only to your group.",
    )
    flagged_item = forms.ModelChoiceField(
        queryset=PackageItem.objects.none(),
        required=False,
        empty_label="Not specified / the whole package",
        label="Book they objected to",
    )
    restock = forms.BooleanField(
        required=False, initial=True, label="Put the books back on the shelf"
    )

    def __init__(self, *args, package: Package, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["flagged_item"].queryset = package.items.all()


class VendorItemForm(forms.Form):
    title = forms.CharField(max_length=300)
    authors = forms.CharField(max_length=300, required=False)
    isbn = forms.CharField(max_length=20, required=False, label="ISBN")
    format = forms.ChoiceField(choices=BookFormat.choices, initial=BookFormat.PAPERBACK)
