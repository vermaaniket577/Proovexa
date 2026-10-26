"""Analysis URL patterns."""
from django.urls import path
from . import views

app_name = 'analysis'

urlpatterns = [
    path('<uuid:doc_id>/start/', views.start_analysis_view, name='start'),
    path('<uuid:doc_id>/quick-scan/', views.quick_scan_view, name='quick_scan'),
    path('<uuid:doc_id>/status/', views.analysis_status_view, name='status'),
    path('exclusion-rules/', views.exclusion_rules_view, name='exclusion_rules'),
    path('ai-settings/', views.ai_settings_view, name='ai_settings'),
    path('ai-settings/test/', views.api_test_ai_connection_view, name='ai_settings_test'),
    path('api/ai-analyze/', views.api_ai_analyze_view, name='api_ai_analyze'),
]
