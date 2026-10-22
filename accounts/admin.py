from django.contrib import admin
from .models import User, Institution, Course, Assignment, AuditLog


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['username', 'email', 'role', 'institution', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'institution']
    search_fields = ['username', 'email', 'first_name', 'last_name']


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ['name', 'short_name', 'domain', 'is_active']
    search_fields = ['name', 'domain']


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'institution', 'instructor', 'is_active']
    list_filter = ['institution', 'is_active']


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'created_by', 'due_date', 'is_active']
    list_filter = ['is_active', 'course']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'resource_type', 'ip_address', 'timestamp']
    list_filter = ['action']
    readonly_fields = ['user', 'action', 'resource_type', 'resource_id', 'details',
                       'ip_address', 'user_agent', 'timestamp']
