from django.contrib.auth.views import LoginView
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.views import View
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy
from django.views.generic import CreateView


class UserLoginView(LoginView):
    template_name = "users/login.html"
    redirect_authenticated_user = True


class RegisterView(CreateView):
    form_class = UserCreationForm
    template_name = "users/register.html"
    success_url = reverse_lazy("users:login")


class UserLogoutView(View):
    def post(self, request, *args, **kwargs):
        logout(request)
        return redirect("users:login")

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)