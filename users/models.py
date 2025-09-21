from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user model replacing Django's default."""

    email = models.EmailField(unique=True)
    contact_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
