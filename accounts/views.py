"""
Account views: login, registration, profile, user management.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.core.paginator import Paginator

from django.db.models import Q
from .forms import LoginForm, RegistrationForm, UserProfileForm, AdminUserForm
from .models import User, AuditLog, Institution
from .decorators import role_required


def login_view(request):
    """User login."""
    if request.user.is_authenticated:
        return redirect('dashboard:home')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            user.last_activity = timezone.now()
            user.save(update_fields=['last_activity'])
            AuditLog.objects.create(
                user=user,
                action=AuditLog.Action.LOGIN,
                ip_address=_get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
            messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
            next_url = request.GET.get('next', 'dashboard:home')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {'form': form})


def register_view(request):
    """User registration."""
    if request.user.is_authenticated:
        return redirect('dashboard:home')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            AuditLog.objects.create(
                user=user,
                action=AuditLog.Action.USER_CREATE,
                resource_type='User',
                resource_id=str(user.id),
                ip_address=_get_client_ip(request),
            )
            login(request, user)
            messages.success(request, 'Registration successful! Welcome to the platform.')
            return redirect('dashboard:home')
    else:
        form = RegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})


def logout_view(request):
    """User logout."""
    if request.user.is_authenticated:
        AuditLog.objects.create(
            user=request.user,
            action=AuditLog.Action.LOGOUT,
            ip_address=_get_client_ip(request),
        )
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('accounts:login')


@login_required
def profile_view(request):
    """View and edit user profile."""
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('accounts:profile')
    else:
        form = UserProfileForm(instance=request.user)

    return render(request, 'accounts/profile.html', {'form': form})


@login_required
@role_required(['admin'])
def user_list_view(request):
    """Admin: list all users."""
    users = User.objects.select_related('institution').all()

    # Filters
    role_filter = request.GET.get('role', '')
    if role_filter:
        users = users.filter(role=role_filter)

    search = request.GET.get('search', '')
    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        )

    paginator = Paginator(users, 20)
    page = request.GET.get('page', 1)
    users_page = paginator.get_page(page)

    return render(request, 'accounts/user_list.html', {
        'users': users_page,
        'role_filter': role_filter,
        'search': search,
    })


@login_required
@role_required(['admin'])
def user_edit_view(request, user_id):
    """Admin: edit a user."""
    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        form = AdminUserForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            AuditLog.objects.create(
                user=request.user,
                action=AuditLog.Action.USER_UPDATE,
                resource_type='User',
                resource_id=str(user.id),
                ip_address=_get_client_ip(request),
            )
            messages.success(request, f'User {user.username} updated.')
            return redirect('accounts:user_list')
    else:
        form = AdminUserForm(instance=user)

    return render(request, 'accounts/user_edit.html', {'form': form, 'edit_user': user})


@login_required
@role_required(['admin'])
def audit_log_view(request):
    """Admin: view audit logs."""
    logs = AuditLog.objects.select_related('user').all()

    action_filter = request.GET.get('action', '')
    if action_filter:
        logs = logs.filter(action=action_filter)

    paginator = Paginator(logs, 50)
    page = request.GET.get('page', 1)
    logs_page = paginator.get_page(page)

    return render(request, 'accounts/audit_log.html', {
        'logs': logs_page,
        'action_filter': action_filter,
        'actions': AuditLog.Action.choices,
    })


def _get_client_ip(request):
    """Extract client IP from request."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')
