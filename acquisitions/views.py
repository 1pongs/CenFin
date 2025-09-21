from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import (
    TemplateView,
    FormView,
    ListView,
    DetailView,
    DeleteView,
    TemplateView,
)
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.db.models import Q
from django.db import transaction
from decimal import Decimal
import json
from urllib.parse import quote_plus
import logging
from django.contrib.auth.decorators import login_required


# Create your views here.

from .models import Acquisition
from .forms import AcquisitionForm, SellAcquisitionForm
from transactions.models import Transaction
from accounts.models import Account
from accounts.forms import AccountForm
from entities.models import Entity
from entities.forms import EntityForm
from currencies.models import Currency

logger = logging.getLogger(__name__)

CARD_FIELDS_BY_CATEGORY = {
    "product": ["date_bought", "amount", "target_selling_date", "status"],
    "stock_bond": [
        "date_bought",
        "amount",
        "current_value",
        "market",
        "target_selling_date",
        "status",
    ],
    "property": [
        "date_bought",
        "amount",
        "location",
        "expected_lifespan_years",
        "status",
    ],
    "equipment": [
        "date_bought",
        "amount",
        "location",
        "expected_lifespan_years",
        "status",
    ],
    "vehicle": [
        "date_bought",
        "amount",
        "model_year",
        "mileage",
        "plate_number",
        "status",
    ],
}

# Short list of fields shown directly on the acquisition cards
CARD_SUMMARY_FIELDS_BY_CATEGORY = {
    "product": ["date_bought", "amount", "status"],
    "stock_bond": ["date_bought", "amount", "status"],
    "property": ["location", "date_bought", "amount", "status"],
    "equipment": ["location", "date_bought", "amount", "status"],
    "vehicle": ["date_bought", "amount", "status"],
}


class AcquisitionListView(ListView):
    model = Acquisition
    template_name = "acquisitions/acquisition_list.html"
    context_object_name = "acquisitions"

    def get_queryset(self):
        qs = Acquisition.objects.select_related("purchase_tx", "sell_tx").filter(
            user=self.request.user, is_deleted=False
        )

        cat = self.request.GET.get("category")
        if cat:
            qs = qs.filter(category=cat)

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)

        status = self.request.GET.get("status")
        if status == "active":
            qs = qs.filter(sell_tx__isnull=True)
        elif status == "not_active":
            qs = qs.filter(sell_tx__isnull=False)

        start = self.request.GET.get("start")
        end = self.request.GET.get("end")
        if start:
            try:
                start_date = timezone.datetime.fromisoformat(start).date()
                qs = qs.filter(purchase_tx__date__gte=start_date)
            except ValueError:
                pass
        if end:
            try:
                end_date = timezone.datetime.fromisoformat(end).date()
                qs = qs.filter(purchase_tx__date__lte=end_date)
            except ValueError:
                pass

        ent = self.request.GET.get("entity")
        if ent:
            qs = qs.filter(purchase_tx__entity_destination_id=ent)

        sort = self.request.GET.get("sort", "name")
        if sort == "balance":
            qs = qs.order_by("-purchase_tx__amount")
        elif sort == "date":
            qs = qs.order_by("-purchase_tx__date")
        else:
            qs = qs.order_by("name")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["current_category"] = self.request.GET.get("category", "")
        ctx["status"] = self.request.GET.get("status", "")
        ctx["start"] = self.request.GET.get("start", "")
        ctx["end"] = self.request.GET.get("end", "")
        ctx["q"] = self.request.GET.get("q", "")
        ctx["sort"] = self.request.GET.get("sort", "name")
        ctx["entity_id"] = self.request.GET.get("entity", "")
        ctx["form"] = AcquisitionForm(user=self.request.user)
        ctx["form"] = AcquisitionForm(user=self.request.user)
        ctx["CARD_FIELDS_BY_CATEGORY"] = CARD_FIELDS_BY_CATEGORY
        ctx["entities"] = (
            Entity.objects.filter(
                Q(user=self.request.user) | Q(user__isnull=True),
                is_active=True,
                is_visible=True,
            )
            .exclude(entity_name="Outside")
            .order_by("entity_name")
        )
        # Inline undo banner (after delete): prefer URL params (works across
        # redirects reliably) and fallback to session keys for backward
        # compatibility.
        undo_acq_id = self.request.GET.get("undo_acq_id")
        undo_acq_name = self.request.GET.get("undo_acq_name")
        if not undo_acq_id:
            undo_acq_id = self.request.session.pop("undo_acq_id", None)
            undo_acq_name = self.request.session.pop("undo_acq_name", None)
        undo_restore_url = None
        if undo_acq_id is not None:
            try:
                undo_restore_url = reverse(
                    "acquisitions:acquisition-restore", args=[undo_acq_id]
                )
            except Exception:
                undo_restore_url = None
        ctx["undo_acq_name"] = undo_acq_name
        ctx["undo_restore_url"] = undo_restore_url
        return ctx


# Archived features removed globally


class AcquisitionCreateView(FormView):
    template_name = "acquisitions/acquisition_form.html"
    form_class = AcquisitionForm
    success_url = reverse_lazy("acquisitions:acquisition-list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        ent_id = self.request.GET.get("entity")
        if ent_id:
            ent = get_object_or_404(Entity, pk=ent_id, user=self.request.user)
            kwargs["locked_entity"] = ent
        cat = self.request.GET.get("category")
        if cat:
            kwargs.setdefault("initial", {})["category"] = cat
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["quick_account_form"] = AccountForm(show_actions=False)
        ctx["quick_entity_form"] = EntityForm(show_actions=False)
        accounts = Account.objects.filter(user=self.request.user, is_active=True)
        account_map = {a.id: (a.currency.code if a.currency else "") for a in accounts}
        ctx["account_currency_map"] = json.dumps(account_map)
        return ctx

    def form_valid(self, form):
        data = form.cleaned_data
        account_src = data["account_source"]
        tx = Transaction(
            user=self.request.user,
            date=data["date"],
            description=data["name"],
            transaction_type="buy acquisition",
            amount=data["amount"],
            currency=getattr(account_src, "currency", None),
            account_source=account_src,
            account_destination=data["account_destination"],
            entity_source=data["entity_source"],
            entity_destination=data["entity_destination"],
            remarks=data["remarks"],
        )
        try:
            tx.full_clean()
        except ValidationError as e:
            form.add_error(None, e.message or e.messages)
            return self.form_invalid(form)
        tx.save()
        Acquisition.objects.create(
            name=data["name"],
            category=data["category"],
            purchase_tx=tx,
            status="active",
            provider=data.get("name") or "",
            user=self.request.user,
        )
        return super().form_valid(form)

    def get_success_url(self):
        # Always return to the Acquisitions list after create
        return super().get_success_url()

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return super().form_invalid(form)


class AcquisitionDetailView(DetailView):
    model = Acquisition
    template_name = "acquisitions/acquisition_detail.html"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("purchase_tx", "sell_tx")
            .filter(user=self.request.user, is_deleted=False)
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        acq: Acquisition = ctx.get("object")
        capital_tx = None
        try:
            # Try to locate the capital return transaction created for this sale.
            # Prefer explicit 'sell acquisition' rows; include legacy 'sell_acquisition'.
            # Some older records stored the capital return as a plain 'transfer'.
            # Include 'transfer' as a fallback so the Edit link can target the
            # correct row instead of sending users to the transactions list.
            from transactions.models import Transaction

            capital_cost = (
                getattr(acq, "purchase_tx", None).amount if getattr(acq, "purchase_tx", None) else Decimal("0")
            ) or Decimal("0")
            if capital_cost and acq and acq.name:
                candidates = (
                    Transaction.objects.filter(
                        user=self.request.user,
                        transaction_type__in=["sell acquisition", "sell_acquisition", "transfer"],
                        amount=capital_cost,
                        description__icontains=acq.name,
                    )
                    .order_by("-date", "-id")
                )
                capital_tx = candidates.first()
        except Exception:
            # Don't block detail rendering if lookup fails
            capital_tx = None
        ctx["capital_return_tx"] = capital_tx
        return ctx


class AcquisitionUpdateView(AcquisitionCreateView):
    def dispatch(self, request, *args, **kwargs):
        self.object = get_object_or_404(
            Acquisition, pk=kwargs["pk"], user=request.user, is_deleted=False
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Expose the acquisition object so templates can show Edit/Delete controls
        ctx["object"] = self.object
        return ctx

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ("GET", "HEAD"):
            tx = self.object.purchase_tx
            initial = {
                "name": self.object.name,
                "category": self.object.category,
            }
            if tx:
                initial.update(
                    {
                        "date": tx.date,
                        "amount": tx.amount,
                        "account_source": tx.account_source_id,
                        "account_destination": tx.account_destination_id,
                        "entity_source": tx.entity_source_id,
                        "entity_destination": tx.entity_destination_id,
                        "remarks": tx.remarks,
                    }
                )
            kwargs["initial"] = initial
        # When editing an acquisition, disable direct edits to the amount
        # to ensure ledger integrity; view will update purchase_tx via
        # controlled code paths instead.
        if self.request.method not in ("POST",):
            # GET forms for editing should show the amount but be disabled
            kwargs["disable_amount"] = True
        return kwargs

    def form_valid(self, form):
        data = form.cleaned_data
        tx = self.object.purchase_tx
        creating_tx = False
        if tx is None:
            tx = Transaction(user=self.request.user, transaction_type="buy acquisition")
            creating_tx = True

        tx.date = data["date"]
        tx.description = data["name"]
        # Preserve existing amount when the form intentionally disables
        # amount editing (defensive server-side guard).
        if form.fields.get("amount") and getattr(
            form.fields["amount"], "disabled", False
        ):
            tx.amount = getattr(tx, "amount", data.get("amount"))
        else:
            tx.amount = data["amount"]
        tx.currency = getattr(data["account_source"], "currency", None)
        tx.account_source = data["account_source"]
        tx.account_destination = data["account_destination"]
        tx.entity_source = data["entity_source"]
        tx.entity_destination = data["entity_destination"]
        tx.remarks = data["remarks"]
        try:
            tx.full_clean()
        except ValidationError as e:
            form.add_error(None, e.message or e.messages)
            return self.form_invalid(form)
        tx.save()
        if creating_tx:
            self.object.purchase_tx = tx
        acq = self.object
        acq.name = data["name"]
        acq.category = data["category"]
        acq.save()
        messages.success(self.request, "Acquisition updated.")
        return super().form_valid(form)


class AcquisitionDeleteView(DeleteView):
    model = Acquisition
    template_name = "acquisitions/acquisition_confirm_delete.html"
    success_url = reverse_lazy("acquisitions:acquisition-list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        # Make deletion + reversal atomic: abort if reversing linked
        # transactions fails so we don't leave the DB in a partial state.
        try:
            from transactions.views import _reverse_and_hide
        except Exception:
            _reverse_and_hide = None

        # Local fallback: in case importing the shared helper fails (e.g.,
        # due to an unexpected import-time error), perform a minimal
        # reversal-and-hide here to preserve ledger correctness.
        def _fallback_reverse_and_hide(txn, actor=None):
            if not txn or getattr(txn, "is_reversal", False) or getattr(txn, "is_reversed", False):
                return
            from transactions.models import Transaction as Tx
            has_both = bool(txn.account_source_id and txn.account_destination_id)
            if has_both and txn.destination_amount is not None:
                amount = txn.destination_amount
                dest_amount = txn.amount
            else:
                amount = txn.amount
                dest_amount = None
            rev = Tx.objects.create(
                user=txn.user,
                date=timezone.now().date(),
                description=f"Reversal of {txn.description}",
                transaction_type=txn.transaction_type,
                amount=amount,
                destination_amount=dest_amount,
                account_source=txn.account_destination,
                account_destination=txn.account_source,
                entity_source=txn.entity_destination,
                entity_destination=txn.entity_source,
                currency=txn.currency,
                is_hidden=True,
                is_reversal=True,
                reversed_transaction=txn,
            )
            # mark and hide original
            txn.is_reversed = True
            txn.reversed_at = timezone.now()
            if actor is not None:
                txn.reversed_by = actor
            txn.ledger_status = "reversed"
            txn.is_hidden = True
            txn.save(update_fields=["is_reversed", "reversed_at", "reversed_by", "ledger_status", "is_hidden"])

        try:
            with transaction.atomic():
                print(
                    f"DBG: AcquisitionDeleteView: starting delete for acquisition {obj.pk} (user={request.user})"
                )
                # Reverse linked transactions; if any reversal raises an
                # exception, the atomic block will roll back.
                if obj.purchase_tx:
                    logger.debug(
                        "Reversing purchase_tx %s for acquisition %s by user %s",
                        obj.purchase_tx_id,
                        obj.pk,
                        request.user,
                    )
                    print(
                        f"DBG: calling reverse-and-hide on purchase_tx {obj.purchase_tx_id}"
                    )
                    try:
                        if _reverse_and_hide:
                            _reverse_and_hide(obj.purchase_tx, actor=request.user)
                        else:
                            _fallback_reverse_and_hide(obj.purchase_tx, actor=request.user)
                    except Exception:
                        # Fallback to local reversal if shared helper raised
                        _fallback_reverse_and_hide(obj.purchase_tx, actor=request.user)
                    # Defensive: ensure flags are set as expected even if helper was partially applied
                    try:
                        from transactions.models import Transaction as Tx
                        ptx = Tx.all_objects.filter(pk=obj.purchase_tx_id).first()
                        if ptx and (not getattr(ptx, "is_hidden", False) or not getattr(ptx, "is_reversed", False)):
                            upd = []
                            if not getattr(ptx, "is_hidden", False):
                                ptx.is_hidden = True
                                upd.append("is_hidden")
                            if not getattr(ptx, "is_reversed", False):
                                ptx.is_reversed = True
                                from django.utils import timezone as _tz
                                ptx.reversed_at = _tz.now()
                                upd.extend(["is_reversed", "reversed_at"])
                            if upd:
                                ptx.ledger_status = "reversed"
                                upd.append("ledger_status")
                                ptx.save(update_fields=upd)
                    except Exception:
                        # Don't block delete on defensive fix
                        pass
                    logger.debug("Reversed purchase_tx %s", obj.purchase_tx_id)
                    print(
                        f"DBG: reverse-and-hide completed for purchase_tx {obj.purchase_tx_id}"
                    )
                if obj.sell_tx:
                    logger.debug(
                        "Reversing sell_tx %s for acquisition %s by user %s",
                        obj.sell_tx_id,
                        obj.pk,
                        request.user,
                    )
                    print(
                        f"DBG: calling reverse-and-hide on sell_tx {obj.sell_tx_id}"
                    )
                    try:
                        if _reverse_and_hide:
                            _reverse_and_hide(obj.sell_tx, actor=request.user)
                        else:
                            _fallback_reverse_and_hide(obj.sell_tx, actor=request.user)
                    except Exception:
                        _fallback_reverse_and_hide(obj.sell_tx, actor=request.user)
                    # Defensive: ensure flags on sale leg too
                    try:
                        from transactions.models import Transaction as Tx
                        stx = Tx.all_objects.filter(pk=obj.sell_tx_id).first()
                        if stx and (not getattr(stx, "is_hidden", False) or not getattr(stx, "is_reversed", False)):
                            upd = []
                            if not getattr(stx, "is_hidden", False):
                                stx.is_hidden = True
                                upd.append("is_hidden")
                            if not getattr(stx, "is_reversed", False):
                                stx.is_reversed = True
                                from django.utils import timezone as _tz
                                stx.reversed_at = _tz.now()
                                upd.extend(["is_reversed", "reversed_at"])
                            if upd:
                                stx.ledger_status = "reversed"
                                upd.append("ledger_status")
                                stx.save(update_fields=upd)
                    except Exception:
                        pass
                    logger.debug("Reversed sell_tx %s", obj.sell_tx_id)
                    print(
                        f"DBG: reverse-and-hide completed for sell_tx {obj.sell_tx_id}"
                    )

                # Also reverse and hide the capital return transaction that
                # accompanies the sale. We didn't store an explicit FK, so
                # locate by type/description/amount and user.
                try:
                    from transactions.models import Transaction as Tx
                    capital_cost = (obj.purchase_tx.amount if obj.purchase_tx else Decimal("0")) or Decimal("0")
                    candidates = Tx.objects.filter(
                        user=request.user,
                        transaction_type__in=["sell acquisition", "sell_acquisition"],
                        amount=capital_cost,
                        description__icontains=obj.name,
                    ).order_by("-date", "-id")
                    for cap_tx in candidates:
                        try:
                            if _reverse_and_hide:
                                _reverse_and_hide(cap_tx, actor=request.user)
                            else:
                                _fallback_reverse_and_hide(cap_tx, actor=request.user)
                        except Exception:
                            _fallback_reverse_and_hide(cap_tx, actor=request.user)
                        # Defensive: ensure flags are set
                        try:
                            from django.utils import timezone as _tz
                            cap = Tx.all_objects.filter(pk=cap_tx.pk).first()
                            if cap and (not getattr(cap, "is_hidden", False) or not getattr(cap, "is_reversed", False)):
                                upd = []
                                if not getattr(cap, "is_hidden", False):
                                    cap.is_hidden = True
                                    upd.append("is_hidden")
                                if not getattr(cap, "is_reversed", False):
                                    cap.is_reversed = True
                                    cap.reversed_at = _tz.now()
                                    upd.extend(["is_reversed", "reversed_at"])
                                if upd:
                                    cap.ledger_status = "reversed"
                                    upd.append("ledger_status")
                                    cap.save(update_fields=upd)
                        except Exception:
                            pass
                except Exception:
                    # Do not block delete if capital lookup fails
                    pass

                # Store undo info in the session BEFORE soft-deleting the
                # acquisition. This reduces the chance that model-side
                # behaviors interfere with session persistence.
                print(f"DBG: setting session undo keys for acq {obj.pk}")
                request.session["undo_acq_id"] = obj.pk
                request.session["undo_acq_name"] = obj.name
                logger.info(
                    "Set undo session for acquisition %s (%s) user=%s",
                    obj.pk,
                    obj.name,
                    request.user,
                )
                # Ensure the session is persisted before redirect so the
                # acquisitions list view can read the undo keys reliably.
                request.session.modified = True
                try:
                    request.session.save()
                    print("DBG: session.save() completed")
                    # Dump session items as seen in the view right after save
                    try:
                        print(
                            "DBG: session contents after save:",
                            dict(request.session.items()),
                        )
                    except Exception:
                        print("DBG: could not read request.session items")
                except Exception:
                    # If the session backend doesn't support explicit save
                    # or it fails for any reason, continue — Django will
                    # still attempt to save the session on response.
                    logger.exception(
                        "Failed to explicitly save session after acquisition delete"
                    )
                    print("DBG: session.save() raised an exception")

                # Soft-delete the acquisition inside the same transaction
                obj.delete()

                # Final enforcement: re-check and enforce flags on linked
                # transactions after soft-delete in case signals or earlier
                # steps failed or were skipped due to unexpected errors.
                try:
                    from transactions.models import Transaction as Tx
                    from django.utils import timezone as _tz
                    def _ensure_flags(txid):
                        if not txid:
                            return
                        t = Tx.all_objects.filter(pk=txid).first()
                        if not t:
                            return
                        updates = []
                        if not getattr(t, "is_hidden", False):
                            t.is_hidden = True
                            updates.append("is_hidden")
                        if not getattr(t, "is_reversed", False):
                            t.is_reversed = True
                            t.reversed_at = _tz.now()
                            t.ledger_status = "reversed"
                            updates.extend(["is_reversed", "reversed_at", "ledger_status"])
                        if updates:
                            t.save(update_fields=updates)
                        # Always hide any child transfer legs as well
                        Tx.all_objects.filter(parent_transfer_id=txid).update(is_hidden=True)

                    _ensure_flags(getattr(obj, "purchase_tx_id", None))
                    _ensure_flags(getattr(obj, "sell_tx_id", None))
                except Exception:
                    # Do not block deletion on enforcement errors
                    pass

        except Exception as e:
            # If anything failed during reversal or deletion, abort and
            # inform the user rather than partially deleting.
            messages.error(request, "Failed to delete acquisition: " + str(e))
            return redirect(reverse("acquisitions:acquisition-detail", args=[obj.pk]))

        undo_url = reverse("acquisitions:acquisition-restore", args=[obj.pk])
        messages.success(
            request,
            "Acquisition deleted. Related transactions (purchase/sale) have been reversed and hidden. "
            + f'<a href="{undo_url}" class="ms-2 btn btn-sm btn-light">Undo</a>',
            extra_tags="safe",
        )
        # Also include undo data on the redirect as GET params so the list
        # view can show the Undo banner without relying on session writes.
        qs = f"?undo_acq_id={quote_plus(str(obj.pk))}"
        if obj.name:
            qs += f"&undo_acq_name={quote_plus(obj.name)}"
        return redirect(self.success_url + qs)


class AcquisitionRestoreView(TemplateView):
    def get(self, request, pk):
        obj = get_object_or_404(Acquisition, pk=pk, user=request.user, is_deleted=True)
        obj.is_deleted = False
        obj.save(update_fields=["is_deleted"])

        # Also attempt to restore any transactions that were reversed when
        # the acquisition was deleted. Reversal rows created by the delete
        # flow have reversed_transaction set to the original; find and
        # remove those reversal rows and un-hide the original transactions.
        try:
            from transactions.models import Transaction

            # Restore purchase_tx
            if obj.purchase_tx_id:
                orig = Transaction.all_objects.filter(pk=obj.purchase_tx_id).first()
                if orig and orig.is_reversed:
                    # delete reversal rows pointed at this original
                    logger.info("Removing reversal rows for purchase_tx %s", orig.id)
                    Transaction.all_objects.filter(
                        reversed_transaction_id=orig.id
                    ).delete()
                    orig.is_hidden = False
                    orig.is_reversed = False
                    orig.ledger_status = "posted"
                    orig.save(
                        update_fields=["is_hidden", "is_reversed", "ledger_status"]
                    )
            # Restore sell_tx
            if obj.sell_tx_id:
                orig2 = Transaction.all_objects.filter(pk=obj.sell_tx_id).first()
                if orig2 and orig2.is_reversed:
                    logger.info("Removing reversal rows for sell_tx %s", orig2.id)
                    Transaction.all_objects.filter(
                        reversed_transaction_id=orig2.id
                    ).delete()
                    orig2.is_hidden = False
                    orig2.is_reversed = False
                    orig2.ledger_status = "posted"
                    orig2.save(
                        update_fields=["is_hidden", "is_reversed", "ledger_status"]
                    )

            # Restore capital return transaction reversed during delete.
            try:
                from decimal import Decimal as _Dec
                cap_amt = (obj.purchase_tx.amount if obj.purchase_tx else _Dec("0")) or _Dec("0")
                caps = Transaction.all_objects.filter(
                    user=request.user,
                    transaction_type__in=["sell acquisition", "sell_acquisition"],
                    amount=cap_amt,
                    description__icontains=obj.name,
                )
                for cap in caps:
                    if getattr(cap, "is_reversed", False):
                        Transaction.all_objects.filter(
                            reversed_transaction_id=cap.id
                        ).delete()
                        cap.is_hidden = False
                        cap.is_reversed = False
                        cap.ledger_status = "posted"
                        cap.save(
                            update_fields=[
                                "is_hidden",
                                "is_reversed",
                                "ledger_status",
                            ]
                        )
            except Exception:
                pass
        except Exception:
            # Don't fail the restore if transaction restore fails.
            pass

        messages.success(request, "Acquisition restored.")
        return redirect(reverse("acquisitions:acquisition-list"))


def sell_acquisition(request, pk):
    acquisition = get_object_or_404(
        Acquisition, pk=pk, user=request.user, is_deleted=False
    )
    if request.method == "POST":
        form = SellAcquisitionForm(request.POST, user=request.user)
        if form.is_valid():
            data = form.cleaned_data
            buy_tx = acquisition.purchase_tx
            capital_cost = buy_tx.amount or Decimal("0")
            profit_amt = data["sale_price"] - capital_cost
            with transaction.atomic():
                # If acquisition already has a recorded sale, update the
                # existing profit transaction and the associated capital
                # return transfer instead of creating duplicates.
                if acquisition.sell_tx:
                    profit_tx = acquisition.sell_tx
                    # Update profit transaction (profit should be an income)
                    profit_tx.date = data["date"]
                    profit_tx.description = f"Sell {acquisition.name} \u2014 profit"
                    profit_tx.transaction_type = "income"
                    profit_tx.amount = profit_amt
                    # Prefer the currency of the selected account_source for
                    # the sale; fall back to the original purchase currency
                    # or any existing Currency row if necessary so full_clean
                    # doesn't reject a blank currency.
                    profit_currency = (
                        getattr(data.get("account_source"), "currency", None)
                        or buy_tx.currency
                        or Currency.objects.first()
                    )
                    profit_tx.currency = profit_currency
                    profit_tx.account_source = data["account_source"]
                    profit_tx.account_destination = data["account_destination"]
                    profit_tx.entity_source = data["entity_source"]
                    profit_tx.entity_destination = data["entity_destination"]
                    profit_tx.remarks = data["remarks"]
                    # Only run full_clean if currency is explicitly set
                    if getattr(profit_tx, "currency", None):
                        profit_tx.full_clean()
                        profit_tx.save()
                    else:
                        profit_tx.save()

                    # Try to find the capital return transaction that belongs to
                    # this sale. Prefer a Sell Acquisition (capital return) or
                    # a transfer with matching amount and description containing the acquisition name.
                    # Debug: list possible matching transactions to help
                    # diagnose why we sometimes fail to find the existing
                    # capital-return transaction and create a duplicate.
                    candidates = list(
                        Transaction.objects.filter(
                            user=request.user,
                            transaction_type__in=[
                                "sell acquisition",
                                "sell_acquisition",
                                "transfer",
                            ],
                            amount=capital_cost,
                            description__icontains=acquisition.name,
                        ).order_by("-date")
                    )
                    logger.debug(
                        "Acquisition sell lookup candidates for acq %s: %s",
                        acquisition.pk,
                        [(t.pk, t.transaction_type, t.description) for t in candidates],
                    )
                    capital_tx = None
                    for t in candidates:
                        if t.pk != getattr(profit_tx, "pk", None):
                            capital_tx = t
                            break
                    if capital_tx:
                        capital_tx.date = data["date"]
                        capital_tx.description = (
                            f"Sell {acquisition.name} \u2014 capital return"
                        )
                        # Ensure capital return uses the 'sell acquisition' type
                        capital_tx.transaction_type = "sell acquisition"
                        capital_tx.account_source = data["account_source"]
                        capital_tx.account_destination = data["account_destination"]
                        capital_tx.entity_source = data["entity_source"]
                        capital_tx.entity_destination = data["entity_destination"]
                        capital_tx.remarks = data["remarks"]
                        # Ensure capital_tx has a currency before validating
                        capital_currency = (
                            getattr(data.get("account_source"), "currency", None)
                            or buy_tx.currency
                            or Currency.objects.first()
                        )
                        capital_tx.currency = capital_currency
                        # Only run full_clean if currency is present; otherwise
                        # allow save() to infer currency from account/user defaults.
                        if getattr(capital_tx, "currency", None):
                            capital_tx.full_clean()
                            capital_tx.save()
                        else:
                            capital_tx.save()
                    else:
                        # If for some reason the capital return is missing,
                        # create it so the sale remains paired. Use
                        # transaction_type 'sell_acquisition' to represent
                        # capital movement associated with the sale.
                        capital_currency = (
                            getattr(data.get("account_source"), "currency", None)
                            or buy_tx.currency
                            or Currency.objects.first()
                        )
                        Transaction.objects.create(
                            user=request.user,
                            date=data["date"],
                            description=f"Sell {acquisition.name} \u2014 capital return",
                            transaction_type="sell acquisition",
                            amount=capital_cost,
                            currency=capital_currency,
                            account_source=data["account_source"],
                            account_destination=data["account_destination"],
                            entity_source=data["entity_source"],
                            entity_destination=data["entity_destination"],
                            remarks=data["remarks"],
                        )
                else:
                    profit_currency = (
                        getattr(data.get("account_source"), "currency", None)
                        or buy_tx.currency
                        or Currency.objects.first()
                    )
                    profit_tx = Transaction.objects.create(
                        user=request.user,
                        date=data["date"],
                        description=f"Sell {acquisition.name} \u2014 profit",
                        transaction_type="income",
                        amount=profit_amt,
                        currency=profit_currency,
                        account_source=data["account_source"],
                        account_destination=data["account_destination"],
                        entity_source=data["entity_source"],
                        entity_destination=data["entity_destination"],
                        remarks=data["remarks"],
                    )
                    capital_currency = (
                        getattr(data.get("account_source"), "currency", None)
                        or buy_tx.currency
                        or Currency.objects.first()
                    )
                    Transaction.objects.create(
                        user=request.user,
                        date=data["date"],
                        description=f"Sell {acquisition.name} \u2014 capital return",
                        transaction_type="sell acquisition",
                        amount=capital_cost,
                        currency=capital_currency,
                        account_source=data["account_source"],
                        account_destination=data["account_destination"],
                        entity_source=data["entity_source"],
                        entity_destination=data["entity_destination"],
                        remarks=data["remarks"],
                    )
                    acquisition.sell_tx = profit_tx
                    acquisition.save()

            return redirect("acquisitions:acquisition-list")
    else:
        try:
            outside_acc = Account.objects.get(account_name="Outside", user__isnull=True)
            src_id = outside_acc.pk
        except Account.DoesNotExist:
            src_id = None
        initial = {
            "date": timezone.now().date(),
            "account_source": src_id,
            "account_destination": acquisition.purchase_tx.account_source_id,
            "entity_source": acquisition.purchase_tx.entity_destination_id,
            "entity_destination": acquisition.purchase_tx.entity_source_id,
        }
        form = SellAcquisitionForm(initial=initial, user=request.user)
    context = {
        "form": form,
        "acquisition": acquisition,
    }
    accounts = Account.objects.filter(user=request.user, is_active=True)
    account_map = {a.id: (a.currency.code if a.currency else "") for a in accounts}
    context["account_currency_map"] = json.dumps(account_map)
    return render(request, "acquisitions/acquisition_sell.html", context)


    
