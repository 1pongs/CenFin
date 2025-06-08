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
from django.views.generic import RedirectView
from django.views.generic import TemplateView
from dashboard.views import DashboardView

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", DashboardView.as_view(), name="dashboard"),
    path('transactions/', include('transactions.urls', namespace='transactions')),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('assets/', include(('assets.urls', 'assets'), namespace='assets')),
    path('entities/', include(('entities.urls', 'entities'), namespace='entities')),

]
