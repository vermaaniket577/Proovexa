"""
Security middleware: rate limiting and audit logging.
"""
import time
from django.core.cache import cache
from django.http import HttpResponse
from django.conf import settings


class HttpResponseTooManyRequests(HttpResponse):
    status_code = 429



class RateLimitMiddleware:
    """Simple in-memory rate limiting middleware."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._rate_limit = getattr(settings, 'RATE_LIMIT_REQUESTS', 100)
        self._window = getattr(settings, 'RATE_LIMIT_WINDOW', 3600)

    def __call__(self, request):
        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return self.get_response(request)

        client_ip = self._get_ip(request)
        cache_key = f'rate_limit:{client_ip}'

        try:
            request_data = cache.get(cache_key)
            if request_data is None:
                request_data = {'count': 0, 'start': time.time()}

            elapsed = time.time() - request_data['start']
            if elapsed > self._window:
                request_data = {'count': 0, 'start': time.time()}

            request_data['count'] += 1
            cache.set(cache_key, request_data, self._window)

            if request_data['count'] > self._rate_limit:
                return HttpResponseTooManyRequests(
                    'Too many requests. Please try again later.'
                )
        except Exception:
            # If cache fails, don't block the request
            pass

        return self.get_response(request)

    def _get_ip(self, request):
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0')


class AuditLogMiddleware:
    """Middleware to track user last activity."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Update last activity for authenticated users (throttled to every 5 minutes)
        if hasattr(request, 'user') and request.user.is_authenticated:
            cache_key = f'last_activity:{request.user.id}'
            if not cache.get(cache_key):
                from .models import User
                User.objects.filter(id=request.user.id).update(
                    last_activity=__import__('django.utils.timezone', fromlist=['now']).now()
                )
                cache.set(cache_key, True, 300)  # 5 minute throttle

        return response
