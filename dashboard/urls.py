from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import DashboardView, MonthlyDataView, MonthlyChartDataView, UserLoginView

app_name = 'dashboard'
urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('monthly-data/', MonthlyDataView.as_view(), name='monthly-data'),
    path('api/chart/monthly/', MonthlyChartDataView.as_view(), name='chart-monthly'),
    path('login/', UserLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='dashboard:dashboard'), name='logout'),
]