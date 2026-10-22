"""Report URL patterns."""
from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.report_list_view, name='list'),
    path('<uuid:report_id>/', views.report_detail_view, name='detail'),
    path('<uuid:report_id>/pdf/', views.download_pdf_view, name='download_pdf'),
    path('<uuid:report_id>/docx/', views.download_docx_view, name='download_docx'),
    path('<uuid:report_id>/json/', views.download_json_view, name='download_json'),
    # AI Writing Detection routes
    path('document/<uuid:doc_id>/ai/', views.ai_report_view, name='ai_report'),
    path('ai/<uuid:ai_report_id>/pdf/', views.download_ai_pdf_view, name='download_ai_pdf'),
]
