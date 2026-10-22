"""
Dashboard views: home, admin stats.
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Avg, Q
from django.utils import timezone
from datetime import timedelta

from documents.models import Document
from analysis.models import SimilarityReport, ProcessingJob
from accounts.models import User, AuditLog, Institution


@login_required
def home_view(request):
    """Main dashboard view - adapts to user role."""
    user = request.user
    context = {'user': user}

    if user.is_admin:
        # Admin dashboard
        context.update(_get_admin_stats())
        return render(request, 'dashboard/admin_home.html', context)
    elif user.is_teacher:
        context.update(_get_teacher_stats(user))
        return render(request, 'dashboard/teacher_home.html', context)
    else:
        context.update(_get_student_stats(user))
        return render(request, 'dashboard/student_home.html', context)


def _get_admin_stats():
    """Get statistics for admin dashboard."""
    now = timezone.now()
    last_30_days = now - timedelta(days=30)
    last_7_days = now - timedelta(days=7)

    total_users = User.objects.count()
    total_documents = Document.objects.filter(is_deleted=False).count()
    total_reports = SimilarityReport.objects.filter(status='completed').count()

    recent_documents = Document.objects.filter(
        is_deleted=False
    ).select_related('uploaded_by').order_by('-uploaded_at')[:10]

    recent_reports = SimilarityReport.objects.filter(
        status='completed'
    ).select_related('document', 'document__uploaded_by').order_by('-created_at')[:10]

    # Usage stats
    docs_this_month = Document.objects.filter(uploaded_at__gte=last_30_days).count()
    docs_this_week = Document.objects.filter(uploaded_at__gte=last_7_days).count()
    avg_similarity = SimilarityReport.objects.filter(
        status='completed'
    ).aggregate(avg=Avg('overall_similarity'))['avg'] or 0

    # User breakdown
    user_counts = User.objects.values('role').annotate(count=Count('id'))

    return {
        'total_users': total_users,
        'total_documents': total_documents,
        'total_reports': total_reports,
        'docs_this_month': docs_this_month,
        'docs_this_week': docs_this_week,
        'avg_similarity': round(avg_similarity, 1),
        'recent_documents': recent_documents,
        'recent_reports': recent_reports,
        'user_counts': {u['role']: u['count'] for u in user_counts},
    }


def _get_teacher_stats(user):
    """Get statistics for teacher dashboard."""
    documents = Document.objects.filter(
        Q(uploaded_by=user) | Q(assignment__created_by=user),
        is_deleted=False
    ).distinct()

    reports = SimilarityReport.objects.filter(
        Q(created_by=user) | Q(document__assignment__created_by=user),
        status='completed'
    ).distinct()

    recent_documents = documents.select_related('uploaded_by').order_by('-uploaded_at')[:10]
    recent_reports = reports.select_related(
        'document', 'document__uploaded_by'
    ).order_by('-created_at')[:10]

    return {
        'total_documents': documents.count(),
        'total_reports': reports.count(),
        'recent_documents': recent_documents,
        'recent_reports': recent_reports,
        'assignments_count': user.created_assignments.filter(is_active=True).count(),
    }


def _get_student_stats(user):
    """Get statistics for student dashboard."""
    documents = Document.objects.filter(
        uploaded_by=user, is_deleted=False
    )
    reports = SimilarityReport.objects.filter(
        document__uploaded_by=user, status='completed'
    )

    recent_documents = documents.order_by('-uploaded_at')[:10]
    recent_reports = reports.select_related('document').order_by('-created_at')[:10]

    return {
        'total_documents': documents.count(),
        'total_reports': reports.count(),
        'recent_documents': recent_documents,
        'recent_reports': recent_reports,
    }
