from django.urls import path
from . import views

app_name = 'insurance'

urlpatterns = [
    path('', views.InsuranceListView.as_view(), name='list'),
    path('new/', views.InsuranceCreateView.as_view(), name='create'),
    path('<int:pk>/edit/', views.InsuranceUpdateView.as_view(), name='edit'),
    path('<int:pk>/delete/', views.InsuranceDeleteView.as_view(), name='delete'),
    path('<int:pk>/', views.InsuranceDetailView.as_view(), name='detail'),
    path('<int:pk>/pay/', views.pay_premium, name='pay-premium'),
    path('api/categories/', views.category_list, name='category-list'),
    path('api/acquisitions/<int:entity_id>/<str:category>/', views.acquisition_options, name='acquisition-options'),
]