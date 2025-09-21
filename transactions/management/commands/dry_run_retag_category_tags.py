from django.core.management.base import BaseCommand
from transactions.models import CategoryTag
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Dry-run report of CategoryTag entries that might be candidates for reassigning transaction_type (e.g. map sell_acquisition flows to income tags)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true", help="Apply changes instead of dry-run"
        )
        parser.add_argument(
            "--user", type=str, help="Username to limit the operation to a single user"
        )
        parser.add_argument(
            "--entity",
            type=int,
            help="Entity id to limit the operation to a single entity",
        )

    def handle(self, *args, **options):
        apply_changes = options.get("apply")
        username = options.get("user")
        entity_id = options.get("entity")

        user_qs = None
        if username:
            User = get_user_model()
            user = User.objects.filter(username=username).first()
            if not user:
                self.stdout.write(self.style.ERROR(f"User '{username}' not found."))
                return
            user_qs = CategoryTag.objects.filter(user=user)
        else:
            user_qs = CategoryTag.objects.all()

        if entity_id:
            user_qs = user_qs.filter(entity_id=entity_id)

        # Candidate tags: those with empty or null transaction_type
        candidates = user_qs.filter(transaction_type__isnull=True) | user_qs.filter(
            transaction_type__exact=""
        )
        candidates = candidates.order_by("user_id", "entity_id", "name")

        if not candidates.exists():
            self.stdout.write(
                "No candidate tags found (no empty transaction_type fields)."
            )
            return

        self.stdout.write(
            self.style.WARNING(
                f"Found {candidates.count()} candidate tag(s) with empty transaction_type."
            )
        )
        for t in candidates:
            self.stdout.write(
                f"User={t.user}, Entity={t.entity_id}, Tag={t.name} (id={t.pk})"
            )

        if not apply_changes:
            self.stdout.write(
                self.style.SUCCESS(
                    "Dry-run complete. Use --apply to assign these tags to a transaction_type."
                )
            )
            return

        # Apply: assign 'income' to candidate tags when the entity has income-tag usage
        changed = 0
        for t in candidates:
            # Heuristic: if any other tag for this user/entity has transaction_type 'income', assume income scope
            has_income = CategoryTag.objects.filter(
                user=t.user, entity_id=t.entity_id, transaction_type="income"
            ).exists()
            if has_income:
                t.transaction_type = "income"
                t.save(update_fields=["transaction_type"])
                changed += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Assigned 'income' to tag id={t.pk} name={t.name} for entity={t.entity_id}"
                    )
                )
            else:
                self.stdout.write(
                    f"Skipping tag id={t.pk} name={t.name} (no evidence of income tags for this entity)"
                )

        self.stdout.write(
            self.style.SUCCESS(f"Applied changes: {changed} tags updated.")
        )
