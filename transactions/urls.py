from django.urls import path
from . import views

app_name = 'transactions'

urlpatterns = [
    path('', views.TransactionListView.as_view(), name='transaction_list'),
    path('new/', views.TransactionCreateView.as_view(), name='transaction_create'),
    path('<int:pk>/edit/', views.TransactionUpdateView.as_view(), name='transaction_update'),
    path("<int:pk>/delete/", views.transaction_delete, name="transaction_delete"),
    
    path("templates/", views.TemplateListView.as_view(), name="template_list"),
    path("templates/new/", views.TemplateCreateView.as_view(), name="template_create"),
    path("templates/<int:pk>/edit/", views.TemplateUpdateView.as_view(), name="template_update"),
    path("templates/<int:pk>/delete/", views.TemplateDeleteView.as_view(), name="template_delete"),
    path('bulk-action/', views.bulk_action, name='bulk_action'),
]
