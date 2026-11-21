from __future__ import annotations

from django import forms
from django.utils import timezone

from shelfpass.correspondence.models import Person, RequestedItem
from shelfpass.facilities.models import Facility


class FacilitySelect(forms.Select):
    """Adds ``data-slug`` to each option so the intake page can fetch rules."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-slug"] = instance.slug
        return option


class FacilityChoiceField(forms.ModelChoiceField):
    widget = FacilitySelect

    def label_from_instance(self, obj: Facility) -> str:
        sample = " (sample)" if obj.is_sample else ""
        return f"{obj.name} — {obj.city}, {obj.state}{sample}"


def facility_field(**kwargs) -> FacilityChoiceField:
    return FacilityChoiceField(
        queryset=Facility.objects.active().order_by("state", "name"),
        empty_label="Choose a facility…",
        **kwargs,
    )


class IntakeForm(forms.Form):
    """The person and envelope details of a letter."""

    name = forms.CharField(max_length=200, label="Name")
    inmate_id = forms.CharField(max_length=40, label="ID number")
    facility = facility_field()
    housing = forms.CharField(max_length=80, required=False, label="Unit / cell")
    received_on = forms.DateField(
        initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"})
    )
    letter_notes = forms.CharField(
        required=False,
        label="Notes from the letter",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Interests, reading level, language, anything else they mentioned.",
    )
    person_id = forms.IntegerField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, organization, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)

    def clean_person_id(self):
        pk = self.cleaned_data.get("person_id")
        if not pk:
            return None
        person = Person.objects.filter(pk=pk, organization=self.organization).first()
        if person is None:
            raise forms.ValidationError("That person record no longer exists.")
        return person

    def clean_received_on(self):
        value = self.cleaned_data["received_on"]
        if value > timezone.localdate():
            raise forms.ValidationError("The letter can't have arrived in the future.")
        return value


class RequestedItemForm(forms.Form):
    description = forms.CharField(
        max_length=300,
        required=False,
        label="Book or topic",
        widget=forms.TextInput(attrs={"placeholder": "e.g. GED study guide, The Hobbit"}),
    )
    author = forms.CharField(max_length=200, required=False)
    kind = forms.ChoiceField(choices=RequestedItem.Kind.choices, initial=RequestedItem.Kind.TITLE)


class BaseRequestedItemFormSet(forms.BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        if not any(f.cleaned_data.get("description", "").strip() for f in self.forms):
            raise forms.ValidationError("Add at least one book or topic they asked for.")

    def items(self) -> list[dict]:
        return [f.cleaned_data for f in self.forms if f.cleaned_data.get("description", "").strip()]


RequestedItemFormSet = forms.formset_factory(
    RequestedItemForm, formset=BaseRequestedItemFormSet, extra=3, max_num=25, validate_max=True
)


class PersonForm(forms.ModelForm):
    facility = facility_field(required=False)

    class Meta:
        model = Person
        fields = ["name", "inmate_id", "facility", "housing", "active", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class AddItemForm(forms.Form):
    description = forms.CharField(max_length=300, label="Book or topic")
    author = forms.CharField(max_length=200, required=False)
    kind = forms.ChoiceField(choices=RequestedItem.Kind.choices)


class CloseRequestForm(forms.Form):
    reason = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Fulfilled, Nothing on the shelf"}),
    )
