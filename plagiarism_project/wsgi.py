"""
WSGI config for plagiarism_project.
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagiarism_project.settings')
application = get_wsgi_application()
