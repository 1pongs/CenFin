from django.urls import path
from .views import UserLogoutView
from . import views

app_name = "users"

urlpatterns = [
    path("login/", views.UserLoginView.as_view(), name="login"),
    path("logout/", UserLogoutView.as_view(), name="logout"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("settings/", views.UserSettingsView.as_view(), name="settings"),
]
