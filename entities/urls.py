from django.urls import path
from . import views
from .views import (
    EntityListView, EntityDetailView, EntityCreateView,
    EntityUpdateView, EntityDeleteView,
    EntityArchivedListView, EntityRestoreView,
    EntityAccountsView
)

app_name='entities'
urlpatterns=[
    path("",EntityListView.as_view(), name="list"),
    path("new/", EntityCreateView.as_view(), name="create"),
    path("archived/", EntityArchivedListView.as_view(), name="archived"),
    path("<int:pk>/edit/", EntityUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", EntityDeleteView.as_view(), name="delete"),
    path("<int:pk>/restore/", EntityRestoreView.as_view(), name="restore"),
    path("<int:pk>/accounts/", EntityAccountsView.as_view(), name="accounts"),
    path("<int:pk>/", EntityDetailView.as_view(), name="detail"),
]