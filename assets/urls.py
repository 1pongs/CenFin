from django.urls import path
from . import views

app_name = 'assets'

urlpatterns = [
    path('', views.AssetListView.as_view(), name='list'),
    path('new/', views.AssetCreateView.as_view(), name='create'),
    path('<int:pk>/sell/', views.sell_asset, name='sell'),
]