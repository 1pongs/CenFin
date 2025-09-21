from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from transactions.models import Transaction
from accounts.models import Account
from entities.models import Entity


class Command(BaseCommand):
    help = (
        "Tag past liquid inflows to a specific account with a destination entity.\n"
        "Use this to align account/entity pair balances (e.g., BDO -> GDER Lending)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--account-id", type=int, help="Account ID to tag", default=None
        )
        parser.add_argument(
            "--account-name",
            type=str,
            help="Account name contains filter (ci)",
            default=None,
        )
        parser.add_argument(
            "--entity-id", type=int, help="Destination Entity ID", default=None
        )
        parser.add_argument(
            "--entity-name", type=str, help="Destination Entity name (ci)", default=None
        )
        parser.add_argument(
            "--user-id", type=int, help="Limit to user id", default=None
        )
        parser.add_argument(
            "--start", type=str, help="Start date ISO (YYYY-MM-DD)", default=None
        )
        parser.add_argument(
            "--end", type=str, help="End date ISO (YYYY-MM-DD)", default=None
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Update even if entity_destination already set",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Do not persist changes"
        )

    def _pick_one(self, qs, kind, ident, name):
        if ident is not None:
            obj = qs.filter(pk=ident).first()
            if not obj:
                raise CommandError(f"{kind} with id={ident} not found")
            return obj
        if name:
            # case-insensitive contains, prefer exact if available
            exact = (
                qs.filter(**{f"{kind.lower()}_name__iexact": name}).first()
                if kind == "Account"
                else qs.filter(entity_name__iexact=name).first()
            )
            if exact:
                return exact
            if kind == "Account":
                qs = qs.filter(account_name__icontains=name)
            else:
                qs = qs.filter(entity_name__icontains=name)
            count = qs.count()
            if count == 0:
                raise CommandError(f"{kind} with name contains '{name}' not found")
            if count > 1:
                raise CommandError(
                    f"{kind} name contains '{name}' matched {count} rows; use --{kind.lower()}-id"
                )
            return qs.first()
        raise CommandError(f"Provide --{kind.lower()}-id or --{kind.lower()}-name")

    def handle(self, *args, **opts):
        user_id = opts.get("user_id")
        acc = self._pick_one(
            Account.objects.all(),
            "Account",
            opts.get("account_id"),
            opts.get("account_name"),
        )
        ent = self._pick_one(
            Entity.objects.all(),
            "Entity",
            opts.get("entity_id"),
            opts.get("entity_name"),
        )

        if acc.account_name == "Outside" or acc.account_type == "Outside":
            raise CommandError("Account must not be Outside")
        if ent.entity_name.lower() == "outside":
            raise CommandError("Entity must not be Outside")

        q = Q(
            account_destination_id=acc.id,
            parent_transfer__isnull=True,
            is_reversal=False,
        )
        q &= Q(asset_type_destination__iexact="liquid")
        if user_id:
            q &= Q(user_id=user_id)
        start = opts.get("start")
        end = opts.get("end")
        if start:
            q &= Q(date__gte=start)
        if end:
            q &= Q(date__lte=end)

        qs = (
            Transaction.all_objects.filter(q)
            .select_related("entity_destination")
            .order_by("date", "id")
        )

        force = opts.get("force")
        dry = opts.get("dry_run")
        scanned = 0
        updated = 0
        for t in qs:
            scanned += 1
            # Only change when dest entity is empty/Account/Outside unless --force
            dest = getattr(t, "entity_destination", None)
            name = (getattr(dest, "entity_name", None) or "").lower()
            if not force:
                if (
                    dest
                    and name not in {"", "account", "outside"}
                    and dest.id == ent.id
                ):
                    continue
                if (
                    dest
                    and name not in {"", "account", "outside"}
                    and dest.id != ent.id
                ):
                    # skip unrelated explicit tagging unless --force
                    continue
            self.stdout.write(
                f"tx#{t.id} {t.date} '{t.description}' -> entity_destination: {name or '[None]'} => {ent.entity_name}"
            )
            if not dry:
                t.entity_destination = ent
                t.save(update_fields=["entity_destination"])
            updated += 1

        self.stdout.write(self.style.SUCCESS(f"Scanned: {scanned}; Updated: {updated}"))
