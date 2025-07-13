from django.db import models
from django.db import models, transaction
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
from transactions.models import Transaction

# Create your models here.

class Acquisition(models.Model):
    """General record of an acquired asset linked to buy/sell transactions."""

    CATEGORY_PRODUCT = "product"
    CATEGORY_STOCK_BOND = "stock_bond"
    CATEGORY_PROPERTY = "property"
    CATEGORY_INSURANCE = "insurance"
    CATEGORY_EQUIPMENT = "equipment"
    CATEGORY_VEHICLE = "vehicle"

    CATEGORY_CHOICES = [
        (CATEGORY_PRODUCT, "Product"),
        (CATEGORY_STOCK_BOND, "Stock/Bond"),
        (CATEGORY_PROPERTY, "Property"),
        (CATEGORY_INSURANCE, "Insurance"),
        (CATEGORY_EQUIPMENT, "Equipment"),
        (CATEGORY_VEHICLE, "Vehicle"),
    ]

    INSURANCE_TYPE_CHOICES = [
        ("vul", "VUL"),
        ("term", "Term"),
        ("whole", "Whole"),
        ("health", "Health"),
    ]

    STATUS_CHOICES = [
        ("inactive", "Inactive"),
        ("active", "Active"),
    ]
    
    name = models.CharField(max_length=255)
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_PRODUCT
    )
    purchase_tx = models.OneToOneField(
        Transaction,
        on_delete=models.CASCADE,
        related_name="acquisition_purchase",
        null=True,
        blank=True,
    )
    sell_tx = models.OneToOneField(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acquisition_sale",
    )

    # stock/bond
    current_value = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    market = models.CharField(max_length=100, blank=True)

    # property
    expected_lifespan_years = models.IntegerField(null=True, blank=True)
    location = models.CharField(max_length=120, blank=True)
    size_sqm = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )

    # universal
    target_selling_date = models.DateField(blank=True, null=True)
    quantity = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    avg_unit_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # vehicle-specific fields
    vehicle_type = models.CharField(max_length=50, blank=True)
    mileage = models.PositiveIntegerField(null=True, blank=True)
    plate_number = models.CharField(max_length=20, blank=True)
    model_year = models.PositiveIntegerField(null=True, blank=True)

    # insurance
    insurance_type = models.CharField(
        max_length=10, choices=INSURANCE_TYPE_CHOICES, blank=True
    )
    sum_assured_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    cash_value = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    maturity_date = models.DateField(null=True, blank=True)
    provider = models.CharField(max_length=255, blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="inactive")
    
    created_at = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="acquisitions",
        null=True,
    )

    class Meta:
        db_table = "acquisitions_acquisition"

    def __str__(self) -> str:
        cat = self.get_category_display()
        return f"{self.name} ({cat})" if cat else self.name

    @property
    def capital_cost(self):
        """Purchase price of the acquisition."""
        return self.purchase_tx.amount or Decimal("0")
    
    @property
    def selling_date(self):
        """Return the date the acquisition was sold, if any."""
        if self.sell_tx:
            return self.sell_tx.date
        return None

    @property
    def price_sold(self):
        """Return the selling price for sellable acquisitions."""
        if not self.sell_tx:
            return None
        purchase_amt = self.purchase_tx.amount or Decimal("0")
        return purchase_amt + (self.sell_tx.amount or Decimal("0"))

    @property
    def profit(self):
        """Return the profit made from selling the acquisition."""
        if self.sell_tx:
            return self.sell_tx.amount or Decimal("0")
        return None

    def recompute_average(self, delta_qty: Decimal, delta_cost: Decimal) -> None:
        """Update quantity and average unit cost."""
        with transaction.atomic():
            new_qty = self.quantity + Decimal(delta_qty)
            total_cost = (self.avg_unit_cost * self.quantity) + Decimal(delta_cost)
            if new_qty <= 0:
                self.quantity = Decimal("0")
                self.avg_unit_cost = Decimal("0")
            else:
                self.quantity = new_qty
                self.avg_unit_cost = total_cost / new_qty
            self.save(update_fields=["quantity", "avg_unit_cost"])

    def sell(
        self, delta_qty: Decimal, sell_price: Decimal, account_dest, sell_date
    ) -> None:
        """Record the sale via paired transactions and update holdings."""
        from accounts.utils import ensure_outside_account
        from entities.utils import ensure_fixed_entities

        outside_acc = ensure_outside_account()
        outside_ent, _ = ensure_fixed_entities(self.user)

        original_cost = self.avg_unit_cost * Decimal(delta_qty)
        profit = Decimal(sell_price) - original_cost

        tx_kwargs = dict(
            user=self.user,
            date=sell_date,
            currency=self.purchase_tx.currency if self.purchase_tx else None,
            account_source=outside_acc,
            account_destination=account_dest,
            entity_source=outside_ent,
            entity_destination=outside_ent,
        )

        with transaction.atomic():
            Transaction.objects.create(
                description=f"Sell {self.name} - capital",
                transaction_type="transfer",
                amount=original_cost,
                **tx_kwargs,
            )
            Transaction.objects.create(
                description=f"Sell {self.name} - {'profit' if profit > 0 else 'loss'}",
                transaction_type="income" if profit > 0 else "expense",
                amount=abs(profit),
                **tx_kwargs,
            )
            self.recompute_average(-delta_qty, -original_cost)
            if self.quantity <= 0:
                self.status = "inactive"
            self.save(update_fields=["status"])