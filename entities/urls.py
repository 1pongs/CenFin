from django.urls import path
from . import views
from .views import EntityListView, EntityAccountDetailView

app_name='entities'
urlpatterns=[
    path("list",EntityListView.as_view(), name="list"),
    path("<int:pk>/", EntityAccountDetailView.as_view(), name="detail"),
]