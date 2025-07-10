from django.db import models
from django.contrib.auth.models import AbstractUser
from currencies.models import Currency, RATE_SOURCE_CHOICES

class User(AbstractUser):
    """Custom user model replacing Django's default."""

    email = models.EmailField(unique=True)
    contact_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    base_currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, null=True, blank=True
    )
    preferred_rate_source = models.CharField(
        max_length=20, choices=RATE_SOURCE_CHOICES, default="XE"
    )