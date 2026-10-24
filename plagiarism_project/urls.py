"""
URL configuration for plagiarism_project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from plagiarism_project.views import (
    landing_page_view,
    health_check,
    custom_page_not_found,
    custom_server_error,
    custom_permission_denied,
    custom_bad_request,
)

urlpatterns = [
    # Marketing Homepage
    path('', landing_page_view, name='landing'),

    # Infrastructure & Monitoring
    path('health/', health_check, name='health_check'),
    path('healthz/', health_check, name='healthz'),

    # Core Applications
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('documents/', include('documents.urls')),
    path('analysis/', include('analysis.urls')),
    path('reports/', include('reports.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('sources/', include('sources.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Production HTTP Error Handlers
handler404 = custom_page_not_found
handler500 = custom_server_error
handler403 = custom_permission_denied
handler400 = custom_bad_request

