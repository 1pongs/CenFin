from django.urls import path
from .views import DashboardView, MonthlyDataView, MonthlyChartDataView

app_name = 'dashboard'
urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('monthly-data/', MonthlyDataView.as_view(), name='monthly-data'),
    path('api/chart/monthly/', MonthlyChartDataView.as_view(), name='chart-monthly'),
]