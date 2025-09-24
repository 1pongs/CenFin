from django.urls import path
from .views import (
    LiabilityListView,
    CreditCardCreateView,
    CreditCardUpdateView,
    CreditCardDeleteView,
    CreditCardRestoreView,
    LoanCreateView,
    LoanUpdateView,
    LoanDeleteView,
    LoanRestoreView,
)

app_name = "liabilities"

urlpatterns = [
    path("", LiabilityListView.as_view(), name="list"),
    path("credit/new/", CreditCardCreateView.as_view(), name="credit-create"),
    path("credit/<int:pk>/edit/", CreditCardUpdateView.as_view(), name="credit-edit"),
    path(
        "credit/<int:pk>/delete/", CreditCardDeleteView.as_view(), name="credit-delete"
    ),
    path(
        "credit/<int:pk>/restore/",
        CreditCardRestoreView.as_view(),
        name="credit-restore",
    ),
    path("loans/new/", LoanCreateView.as_view(), name="loan-create"),
    path("loans/<int:pk>/edit/", LoanUpdateView.as_view(), name="loan-edit"),
    # Legacy/alias route name expected by some tests
    path("loans/<int:pk>/edit/", LoanUpdateView.as_view(), name="loan-update"),
    path("loans/<int:pk>/delete/", LoanDeleteView.as_view(), name="loan-delete"),
    path("loans/<int:pk>/restore/", LoanRestoreView.as_view(), name="loan-restore"),
]
