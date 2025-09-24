from django.urls import path
from . import views

app_name = "transactions"

urlpatterns = [
    path("", views.TransactionListView.as_view(), name="transaction_list"),
    path("new/", views.TransactionCreateView.as_view(), name="transaction_create"),
    path(
        "<int:pk>/edit/",
        views.TransactionUpdateView.as_view(),
        name="transaction_update",
    ),
    # Legacy/alias route name expected by some tests
    path(
        "<int:pk>/edit/",
        views.TransactionUpdateView.as_view(),
        name="transaction_edit",
    ),
    path("<int:pk>/delete/", views.transaction_delete, name="transaction_delete"),
    path(
        "<int:pk>/correct/",
        views.TransactionCorrectView.as_view(),
        name="transaction_correct",
    ),
    path(
        "<int:pk>/undo-delete/",
        views.transaction_undo_delete,
        name="transaction_undo_delete",
    ),
    path("templates/", views.TemplateListView.as_view(), name="template_list"),
    path("templates/new/", views.TemplateCreateView.as_view(), name="template_create"),
    path(
        "templates/<int:pk>/edit/",
        views.TemplateUpdateView.as_view(),
        name="template_update",
    ),
    path(
        "templates/<int:pk>/delete/",
        views.TemplateDeleteView.as_view(),
        name="template_delete",
    ),
    path("tags/undo-delete/", views.tag_undo_delete, name="tag_undo_delete"),
    path("bulk-action/", views.bulk_action, name="bulk_action"),
    path("pair-balance/", views.pair_balance, name="pair_balance"),
    path("categories/", views.category_manager, name="category_manager"),
    # Accept both with and without trailing slash to avoid APPEND_SLASH 301s
    path("tags/", views.tags, name="tags"),
    path("tags", views.tags),  # no-name variant without slash
    path("tags/<int:pk>/", views.tag_detail, name="tag_detail"),
    path("tags/<int:pk>", views.tag_detail),  # no-name variant without slash
    path(
        "summary/entity/<int:entity_id>/",
        views.entity_category_summary,
        name="entity_category_summary",
    ),
    # E2E helper (development only)
    path(
        "e2e/create-test-user/", views.e2e_create_test_user, name="e2e_create_test_user"
    ),
]
