"""
User models with role-based access control.
"""
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Institution(models.Model):
    """Academic institution or organization."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    short_name = models.CharField(max_length=50, blank=True)
    domain = models.CharField(max_length=255, blank=True, help_text="Email domain for auto-association")
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['domain']),
        ]

    def __str__(self):
        return self.name


class User(AbstractUser):
    """Custom user model with role-based access."""
    
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Administrator'
        TEACHER = 'teacher', 'Teacher / Researcher'
        STUDENT = 'student', 'Student / Author'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    institution = models.ForeignKey(
        Institution, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='users'
    )
    department = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    last_activity = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['institution']),
        ]

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    def can_manage_users(self):
        return self.is_admin

    def can_create_assignments(self):
        return self.is_admin or self.is_teacher

    def can_view_all_reports(self):
        return self.is_admin

    def can_compare_submissions(self):
        return self.is_admin or self.is_teacher


class Course(models.Model):
    """Academic course within an institution."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    institution = models.ForeignKey(
        Institution, on_delete=models.CASCADE, related_name='courses'
    )
    instructor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='taught_courses'
    )
    students = models.ManyToManyField(User, blank=True, related_name='enrolled_courses')
    academic_year = models.CharField(max_length=20, blank=True)
    semester = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['institution', 'code']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}" if self.code else self.name


class Assignment(models.Model):
    """Assignment within a course for plagiarism checking."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name='assignments'
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='created_assignments'
    )
    due_date = models.DateTimeField(null=True, blank=True)
    max_similarity_threshold = models.IntegerField(
        default=25,
        help_text="Maximum acceptable similarity percentage"
    )
    allow_self_comparison = models.BooleanField(
        default=True,
        help_text="Compare submissions within this assignment against each other"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class AuditLog(models.Model):
    """Audit trail for security-sensitive actions."""
    
    class Action(models.TextChoices):
        LOGIN = 'login', 'Login'
        LOGOUT = 'logout', 'Logout'
        UPLOAD = 'upload', 'Document Upload'
        DELETE = 'delete', 'Document Delete'
        ANALYZE = 'analyze', 'Run Analysis'
        REPORT_VIEW = 'report_view', 'Report Viewed'
        REPORT_DOWNLOAD = 'report_download', 'Report Downloaded'
        USER_CREATE = 'user_create', 'User Created'
        USER_UPDATE = 'user_update', 'User Updated'
        SETTINGS_CHANGE = 'settings_change', 'Settings Changed'
        PERMISSION_CHANGE = 'permission_change', 'Permission Changed'

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='audit_logs'
    )
    action = models.CharField(max_length=50, choices=Action.choices)
    resource_type = models.CharField(max_length=100, blank=True)
    resource_id = models.CharField(max_length=255, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.user} - {self.get_action_display()} at {self.timestamp}"
