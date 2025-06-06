from django.urls import path
from . import views
from .views import AccountCreateView

app_name = 'accounts'
urlpatterns = [
    path('', views.account_list, name='list'),
    path('new/', AccountCreateView.as_view(), name='create'),
]
