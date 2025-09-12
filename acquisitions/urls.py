from django.urls import path
from . import views

app_name = 'acquisitions'

urlpatterns = [
    path('', views.AcquisitionListView.as_view(), name='acquisition-list'),
    path('new/', views.AcquisitionCreateView.as_view(), name='acquisition-create'),
    path('<int:pk>/', views.AcquisitionDetailView.as_view(), name='acquisition-detail'),
    path('<int:pk>/edit/', views.AcquisitionUpdateView.as_view(), name='acquisition-update'),
    path('<int:pk>/delete/', views.AcquisitionDeleteView.as_view(), name='acquisition-delete'),
    path('<int:pk>/restore/', views.AcquisitionRestoreView.as_view(), name='acquisition-restore'),
    path('<int:pk>/sell/', views.sell_acquisition, name='sell'),
]
