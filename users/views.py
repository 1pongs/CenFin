from django.contrib.auth.views import LoginView
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.views import View

from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView
from django.contrib import messages
from django.contrib.auth import get_user_model

from .forms import UserSettingsForm, CustomUserCreationForm

class UserLoginView(LoginView):
    template_name = "users/login.html"
    redirect_authenticated_user = True

class RegisterView(CreateView):
    form_class = CustomUserCreationForm
    template_name = "users/register.html"
    success_url = reverse_lazy("users:login")

class UserLogoutView(View):
    def post(self, request, *args, **kwargs):
        logout(request)
        return redirect("users:login")

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)

class UserSettingsView(UpdateView):
    model = get_user_model()
    form_class = UserSettingsForm
    template_name = "users/account_settings.html"
    success_url = reverse_lazy("users:settings")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Account settings updated.")
        return super().form_valid(form)