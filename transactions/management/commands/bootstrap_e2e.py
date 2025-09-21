from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = (
        "Bootstrap minimal E2E test data: user, fixed entities/accounts, and a template"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username", default="testuser", help="Username for test user"
        )
        parser.add_argument(
            "--password", default="testpass", help="Password for test user"
        )
        parser.add_argument(
            "--email", default="test@example.com", help="Email for test user"
        )

    def handle(self, *args, **options):
        username = options.get("username")
        password = options.get("password")
        email = options.get("email")

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username, defaults={"email": email}
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created user {username}"))
        else:
            self.stdout.write(f"Using existing user {username}")

        # Ensure password is set to the requested value (useful on repeated runs)
        user.set_password(password)
        user.email = email
        user.save()

        # Defer imports that depend on project settings
        from entities.utils import ensure_fixed_entities
        from accounts.utils import ensure_outside_account
        from accounts.models import Account
        from transactions.models import TransactionTemplate

        # Ensure fixed entities for this user (creates Outside/Account entities scoped to user)
        outside_entity, account_entity = ensure_fixed_entities(user)
        self.stdout.write(
            self.style.SUCCESS(
                f'Ensured fixed entities for user {username}: Outside entity id={getattr(outside_entity,"id",None)}'
            )
        )

        # Ensure global Outside account exists
        outside_account = ensure_outside_account()
        self.stdout.write(
            self.style.SUCCESS(
                f'Ensured global Outside account id={getattr(outside_account,"id",None)}'
            )
        )

        # Create a visible sample account for the user (idempotent)
        acc, acc_created = Account.objects.get_or_create(
            account_name=f"E2E Account {username}",
            user=user,
            defaults={"account_type": "Banks"},
        )
        if acc_created:
            self.stdout.write(
                self.style.SUCCESS(f"Created account {acc} for user {username}")
            )
        else:
            self.stdout.write(f"Using existing account {acc} for user {username}")

        # Create a per-user template with autopop_map referencing Outside values
        tpl_name = f"e2e-template-{username}"
        autopop = {"transaction_type": "expense"}
        if outside_account:
            autopop["account_destination"] = outside_account.id
        if outside_entity:
            autopop["entity_destination"] = outside_entity.id

        tpl, tpl_created = TransactionTemplate.objects.get_or_create(
            name=tpl_name, defaults={"user": user, "autopop_map": autopop}
        )
        if tpl_created:
            self.stdout.write(
                self.style.SUCCESS(f"Created template {tpl_name} (id={tpl.id})")
            )
        else:
            # Ensure template owned by this user and autopop_map is present
            tpl.user = user
            tpl.autopop_map = tpl.autopop_map or autopop
            tpl.save(update_fields=["user", "autopop_map"])
            self.stdout.write(f"Updated existing template {tpl_name} (id={tpl.id})")

        self.stdout.write(self.style.SUCCESS("E2E bootstrap complete."))
