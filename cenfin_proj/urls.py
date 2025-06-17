"""
URL configuration for cenfin_proj project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from transactions import views as txn_api_views
from accounts.views import api_create_account
from entities.views import api_create_entity
from transactions.views import api_create_template

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include(('dashboard.urls', 'dashboard'), namespace='dashboard')),
    path('api/balance/account/<int:pk>/', txn_api_views.account_balance, name='api_account_balance'),
    path('api/balance/entity/<int:pk>/', txn_api_views.entity_balance, name='api_entity_balance'),
    path('api/create/account/', api_create_account, name='api_create_account'),
    path('api/create/entity/', api_create_entity, name='api_create_entity'),
    path('api/create/template/', api_create_template, name='api_create_template'),
    path('transactions/', include('transactions.urls', namespace='transactions')),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('acquisitions/', include(('acquisitions.urls', 'acquisitions'), namespace='acquisitions')),
    path('entities/', include(('entities.urls', 'entities'), namespace='entities')),
    path('users/', include('users.urls', namespace='users')),
]
