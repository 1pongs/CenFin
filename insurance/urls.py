from django.urls import path
from . import views

app_name = 'insurance'

urlpatterns = [
    path('', views.InsuranceListView.as_view(), name='list'),
    path('new/', views.InsuranceCreateView.as_view(), name='create'),
    path('<int:pk>/', views.InsuranceDetailView.as_view(), name='detail'),
]