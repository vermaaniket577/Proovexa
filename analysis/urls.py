"""Analysis URL patterns."""
from django.urls import path
from . import views

app_name = 'analysis'

urlpatterns = [
    path('<uuid:doc_id>/start/', views.start_analysis_view, name='start'),
    path('<uuid:doc_id>/status/', views.analysis_status_view, name='status'),
    path('exclusion-rules/', views.exclusion_rules_view, name='exclusion_rules'),
]
