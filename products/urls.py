from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    path('', views.ProductListView.as_view(), name='list'),
    path('new/', views.ProductCreateView.as_view(), name='create'),
    path('<int:pk>/sell/', views.sell_product, name='sell'),
]