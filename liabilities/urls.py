from django.urls import path
from .views import LiabilityListView, CreditCardCreateView, LoanCreateView

app_name = 'liabilities'

urlpatterns = [
    path('', LiabilityListView.as_view(), name='list'),
    path('credit/new/', CreditCardCreateView.as_view(), name='credit-create'),
    path('loans/new/', LoanCreateView.as_view(), name='loan-create'),
]