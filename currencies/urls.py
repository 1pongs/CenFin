from django.urls import path
from . import views

app_name = 'currencies'

urlpatterns = [
    path('active/', views.active_currencies, name='active-currencies'),
    path('api/currencies/', views.api_currencies, name='currency-list'),
]