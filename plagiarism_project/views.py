"""
Core utility views and error handlers for plagiarism_project.
"""
# pyrefly: ignore[missing-import]
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.conf import settings
import shutil
import os


def health_check(request):
    """
    Health check endpoint for load balancers, container orchestrators,
    and monitoring uptime systems (Kubernetes, AWS ALB, Render, Railway).
    """
    status = {
        "status": "healthy",
        "service": "turnitin-plagiarism-core",
        "version": getattr(settings, "ANALYSIS_ENGINE_VERSION", "1.0.0"),
    }
    status_code = 200

    # 1. Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        status["database"] = "ok"
    except Exception as e:
        status["database"] = f"error: {str(e)}"
        status["status"] = "unhealthy"
        status_code = 503

    # 2. Upload storage writability check
    try:
        upload_root = getattr(settings, "UPLOAD_ROOT", None) or settings.MEDIA_ROOT
        os.makedirs(upload_root, exist_ok=True)
        test_file = os.path.join(upload_root, ".health_check_tmp")
        with open(test_file, "w") as f:
            f.write("ok")
        if os.path.exists(test_file):
            os.remove(test_file)
        status["storage"] = "writable"
    except Exception as e:
        status["storage"] = f"warning: {str(e)}"

    return JsonResponse(status, status=status_code)


def custom_page_not_found(request, exception=None):
    """Render friendly 404 page."""
    return render(request, "404.html", status=404)


def custom_server_error(request):
    """Render friendly 500 page with logging."""
    import traceback
    traceback.print_exc()
    return render(request, "500.html", status=500)


def custom_permission_denied(request, exception=None):
    """Render friendly 403 page."""
    return render(request, "403.html", status=403)


def custom_bad_request(request, exception=None):
    """Render friendly 400 page."""
    return render(request, "400.html", status=400)
