from django.urls import path

from . import views

urlpatterns = [
    path("csrf/", views.CsrfView.as_view(), name="auth-csrf"),
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/", views.MeView.as_view(), name="auth-me"),
    path("options/", views.OptionsView.as_view(), name="auth-options"),
    path("signup/", views.SignupView.as_view(), name="auth-signup"),
    path("password/", views.ChangePasswordView.as_view(), name="auth-password"),
]
