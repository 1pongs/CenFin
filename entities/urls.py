from django.urls import path
from . import views
from .views import (
    EntityListView, EntityDetailView, EntityCreateView,
    EntityUpdateView, EntityDeleteView,
    EntityArchivedListView, EntityRestoreView,
    EntityAccountsView,
    EntityAnalyticsView,
    entity_kpis,
    entity_category_summary_api,
    entity_category_timeseries_api,
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
    path("<int:pk>/analytics/", EntityAnalyticsView.as_view(), name="analytics"),
    # APIs for analytics
    path("<int:pk>/analytics/kpis/", entity_kpis, name="analytics-kpis"),
    path("<int:pk>/analytics/category-summary/", entity_category_summary_api, name="analytics-category-summary"),
    path("<int:pk>/analytics/category-timeseries/", entity_category_timeseries_api, name="analytics-category-timeseries"),
    path("<int:pk>/", EntityDetailView.as_view(), name="detail"),
]
