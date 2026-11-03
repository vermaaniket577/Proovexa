"""Sources URL patterns."""
from django.urls import path
from . import views

app_name = 'sources'

urlpatterns = [
    path('providers/', views.source_providers_view, name='providers'),
    path('test/<slug:connector_id>/', views.test_connector_api_view, name='test_connector'),
]
