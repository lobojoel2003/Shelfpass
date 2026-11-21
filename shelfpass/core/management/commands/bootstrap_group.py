"""Create a group and its first coordinator account (for fresh installs)."""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from shelfpass.orgs.models import Membership, Organization


class Command(BaseCommand):
    help = "Create a books-to-prisoners group and a coordinator who can log in."

    def add_arguments(self, parser):
        parser.add_argument(
            "--name", required=True, help="Group name, e.g. 'Riverside Books to Prisoners'."
        )
        parser.add_argument("--return-address", default="", help="Use \\n between lines.")
        parser.add_argument("--username", required=True, help="Coordinator username.")
        parser.add_argument("--email", default="")
        parser.add_argument(
            "--password-env",
            default="SHELFPASS_BOOTSTRAP_PASSWORD",
            help="Environment variable holding the coordinator's password.",
        )
        parser.add_argument(
            "--superuser", action="store_true", help="Also give Django admin access."
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        password = os.environ.get(opts["password_env"], "")
        if len(password) < 10:
            raise CommandError(
                f"Set {opts['password_env']} to a password of at least 10 characters."
            )
        User = get_user_model()
        if User.objects.filter(username=opts["username"]).exists():
            raise CommandError(f"User {opts['username']!r} already exists.")
        org, created = Organization.objects.get_or_create(
            name=opts["name"],
            defaults={
                "return_address": opts["return_address"].replace("\\n", "\n") or opts["name"]
            },
        )
        create = User.objects.create_superuser if opts["superuser"] else User.objects.create_user
        user = create(username=opts["username"], email=opts["email"], password=password)
        Membership.objects.create(user=user, organization=org, role=Membership.Role.COORDINATOR)
        verb = "Created" if created else "Joined existing"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} group {org.name!r}; coordinator {user.username!r} can now log in."
            )
        )
