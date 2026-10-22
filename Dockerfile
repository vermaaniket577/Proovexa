# ==============================================================================
# Production Dockerfile for ScholarGuard Plagiarism Detection Platform
# ==============================================================================
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies for PyMuPDF, ReportLab, and MySQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . /app/

# Create persistent storage directories
RUN mkdir -p /app/media /app/secure_uploads /app/staticfiles

# Collect static files into staticfiles directory
RUN python manage.py collectstatic --noinput

# Create non-root user for enhanced security
RUN useradd -u 1000 -U -s /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose standard web port
EXPOSE 8000

# Health check using built-in /health/ endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health/ || exit 1

# Start production server using Gunicorn
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn plagiarism_project.wsgi:application --bind 0.0.0.0:${PORT} --workers 3 --threads 2 --timeout 120"]
