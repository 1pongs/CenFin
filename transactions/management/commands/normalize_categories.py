from django.core.management.base import BaseCommand
from django.db import transaction
from transactions.models import Transaction


class Command(BaseCommand):
    help = (
        "Normalize transaction categories: for transactions with multiple categories, "
        "keep a single primary category and remove the rest."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Apply changes. Omit to run in dry-run mode.",
        )
        parser.add_argument(
            "--pick",
            choices=["oldest", "newest"],
            default="oldest",
            help="How to pick the primary category when multiple exist (default: oldest).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limit processing to N transactions (0 = all).",
        )

    def handle(self, *args, **options):
        commit = options.get("commit")
        pick = options.get("pick")
        limit = options.get("limit")

        qs = Transaction.all_objects.filter(categories__isnull=False).distinct()
        # annotate count via Python to avoid DB-specific functions
        candidates = []
        for tx in qs.iterator():
            cnt = tx.categories.count()
            if cnt > 1:
                candidates.append(tx.pk)
                if limit and len(candidates) >= limit:
                    break

        if not candidates:
            self.stdout.write(
                self.style.SUCCESS("No transactions found with multiple categories.")
            )
            return

        self.stdout.write(
            self.style.WARNING(
                f"Found {len(candidates)} transactions with multiple categories."
            )
        )

        if not commit:
            self.stdout.write(
                self.style.NOTICE(
                    "Dry-run mode (no changes will be applied). Use --commit to apply."
                )
            )

        processed = 0
        changed = 0
        with transaction.atomic():
            for pk in candidates:
                tx = (
                    Transaction.all_objects.select_related("user")
                    .prefetch_related("categories")
                    .get(pk=pk)
                )
                cats = list(tx.categories.order_by("created_at").all())
                if not cats or len(cats) <= 1:
                    continue
                processed += 1
                if pick == "oldest":
                    primary = cats[0]
                else:
                    primary = cats[-1]
                others = [c for c in cats if c.pk != primary.pk]
                self.stdout.write(
                    f"Transaction {tx.pk} (user={tx.user_id}) -> keep: {primary.name} ({primary.pk}), remove: {[o.name for o in others]}"
                )
                if commit:
                    tx.categories.set([primary])
                    changed += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {processed} transactions; changed: {changed}"
            )
        )
