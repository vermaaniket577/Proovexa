"""Account URL patterns."""
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('users/', views.user_list_view, name='user_list'),
    path('users/<uuid:user_id>/edit/', views.user_edit_view, name='user_edit'),
    path('audit-log/', views.audit_log_view, name='audit_log'),
]
