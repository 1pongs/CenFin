from django.db import models

# Create your models here.

class AccountQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

class Account(models.Model):
    account_type_choices = [
        ('Banks', 'Banks'),
        ('E-Wallet', 'E-Wallet'),
        ('Cash','Cash-on-Hand'),
        ('Others','Others'),
    ]
    account_name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=50, choices=account_type_choices)
    is_active = models.BooleanField(default=True)

    objects=AccountQuerySet.as_manager()

    def delete(self, *args, **kwargs):
        self.is_active=False
        self.save()

    def __str__(self):
        return self.account_name