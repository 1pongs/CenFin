from django.urls import path
from . import views
from .views import (
    AccountCreateView, AccountUpdateView, AccountDeleteView,
    AccountArchivedListView, AccountRestoreView
)

app_name = 'accounts'
urlpatterns = [
    path('', views.account_list, name='list'),
    path('new/', AccountCreateView.as_view(), name='create'),
    path('archived/', AccountArchivedListView.as_view(), name='archived'),
    path('<int:pk>/edit/', AccountUpdateView.as_view(), name='edit'),
    path('<int:pk>/delete/', AccountDeleteView.as_view(), name='delete'),
    path('<int:pk>/restore/', AccountRestoreView.as_view(), name='restore'),
]
