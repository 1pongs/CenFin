from django.urls import path
from .views import LiabilityListView

app_name = 'liabilities'

urlpatterns = [
    path('', LiabilityListView.as_view(), name='list'),
]