from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from shelfpass.orgs.models import Membership, Organization


class OrganizationForm(forms.ModelForm):
    website = forms.URLField(required=False, assume_scheme="https")

    class Meta:
        model = Organization
        fields = [
            "name",
            "return_address",
            "contact_email",
            "website",
            "packing_slip_note",
            "share_rejections",
        ]
        widgets = {
            "return_address": forms.Textarea(attrs={"rows": 4}),
            "packing_slip_note": forms.Textarea(attrs={"rows": 3}),
        }


class MemberAddForm(forms.Form):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    role = forms.ChoiceField(choices=Membership.Role.choices, initial=Membership.Role.VOLUNTEER)
    password = forms.CharField(
        widget=forms.PasswordInput(render_value=False),
        help_text="A temporary password. Ask them to change it after logging in.",
    )

    def __init__(self, *args, organization: Organization, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        user = get_user_model().objects.filter(username__iexact=username).first()
        if user and Membership.objects.filter(user=user, organization=self.organization).exists():
            raise forms.ValidationError("That volunteer is already in this group.")
        if user:
            raise forms.ValidationError(
                "That username is taken. Pick another, or ask an admin to add the existing account."
            )
        return username

    def clean(self):
        data = super().clean()
        if data.get("password"):
            user = get_user_model()(
                username=data.get("username", ""),
                email=data.get("email", ""),
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
            )
            try:
                validate_password(data["password"], user)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return data

    def save(self) -> Membership:
        data = self.cleaned_data
        user = get_user_model().objects.create_user(
            username=data["username"],
            email=data.get("email", ""),
            password=data["password"],
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
        )
        return Membership.objects.create(
            user=user, organization=self.organization, role=data["role"]
        )


class MembershipRoleForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = ["role"]
