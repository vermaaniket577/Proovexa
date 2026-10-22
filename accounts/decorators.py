"""
Role-based access decorators.
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import HttpResponseForbidden


def role_required(allowed_roles):
    """Decorator to restrict views to specific user roles."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('accounts:login')
            
            user_role = request.user.role
            # Superusers and admins always pass
            if request.user.is_superuser or user_role == 'admin':
                return view_func(request, *args, **kwargs)
            
            if user_role in allowed_roles:
                return view_func(request, *args, **kwargs)
            
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('dashboard:home')
        return wrapper
    return decorator


def teacher_or_admin_required(view_func):
    """Shortcut: require teacher or admin role."""
    return role_required(['admin', 'teacher'])(view_func)


def admin_required(view_func):
    """Shortcut: require admin role."""
    return role_required(['admin'])(view_func)
