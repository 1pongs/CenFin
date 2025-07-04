from django.urls import path
from .views import DashboardView, MonthlyDataView, MonthlyChartDataView
from .api import dashboard_data, top10_data

app_name = 'dashboard'
urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('monthly-data/', MonthlyDataView.as_view(), name='monthly-data'),
    path('api/chart/monthly/', MonthlyChartDataView.as_view(), name='chart-monthly'),
    path('api/dashboard-data/', dashboard_data, name='dashboard-data'),
    path('api/top10/', top10_data, name='top10-data'),
]