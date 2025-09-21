from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from decimal import Decimal
from liabilities.models import Loan


class LoanImmutabilityTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="lu", password="p")
        self.client.login(username="lu", password="p")
        # Create a loan
        self.loan = Loan.objects.create(
            user=self.user,
            principal_amount=Decimal("1000.00"),
            interest_rate=5,
            received_date="2020-01-01",
        )

    def test_principal_preserved_on_update(self):
        url = reverse("liabilities:loan-update", args=[self.loan.pk])
        self.client.post(
            url,
            {
                "lender_text": "",
                "principal_amount": "1.00",
                "interest_rate": "5",
                "received_date": "2020-01-01",
                "currency": "",
                "save": "Save",
            },
            follow=True,
        )
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.principal_amount, Decimal("1000.00"))
