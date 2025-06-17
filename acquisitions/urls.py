from django.urls import path
from . import views

app_name = 'acquisitions'

urlpatterns = [
    path('', views.AcquisitionListView.as_view(), name='list'),
    path('new/', views.AcquisitionCreateView.as_view(), name='create'),
    path('<int:pk>/sell/', views.sell_acquisition, name='sell'),
]