from django.urls import path
from . import views

app_name = 'currencies'

urlpatterns = [
    path('rates/', views.ExchangeRateListView.as_view(), name='rate-list'),
    path('rates/new/', views.ExchangeRateCreateView.as_view(), name='rate-create'),
    path('rates/<int:pk>/edit/', views.ExchangeRateUpdateView.as_view(), name='rate-edit'),
    path('rates/<int:pk>/delete/', views.ExchangeRateDeleteView.as_view(), name='rate-delete'),
    path('active/', views.active_currencies, name='active-currencies'),
    path('api/currencies/', views.api_currencies, name='currency-list'),
]