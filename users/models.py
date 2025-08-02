from django.db import models
from django.contrib.auth.models import AbstractUser
from currencies.models import Currency

class User(AbstractUser):
    """Custom user model replacing Django's default."""

    email = models.EmailField(unique=True)
    contact_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    base_currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, null=True, blank=True
    )