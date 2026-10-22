"""
Production WSGI Runner for Windows and Cross-Platform Environments.
Uses Waitress (multi-threaded, production-grade WSGI server).
Run with: python run_production.py
"""
import os
import sys

# Ensure settings module is configured
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagiarism_project.settings')

try:
    import django
    django.setup()
    from django.core.wsgi import get_wsgi_application
    from waitress import serve
except ImportError as e:
    print(f"Error loading dependencies: {e}")
    print("Please install requirements: pip install -r requirements.txt")
    sys.exit(1)

if __name__ == '__main__':
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 8000))
    threads = int(os.getenv('WAITRESS_THREADS', 6))

    application = get_wsgi_application()

    print(f"============================================================")
    print(f" ScholarGuard Production Server (Waitress)")
    print(f" Running at: http://{host}:{port}/")
    print(f" Threads:    {threads}")
    print(f" Health:     http://{host}:{port}/health/")
    print(f"============================================================")

    serve(application, host=host, port=port, threads=threads)
