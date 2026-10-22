"""
Report views: view, download (PDF/DOCX/JSON), and list reports.
"""
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.core.paginator import Paginator

from analysis.models import SimilarityReport, MatchedPassage, AIReport
from documents.models import Document
from accounts.models import AuditLog
from .pdf_generator import generate_pdf_report
from .docx_generator import generate_docx_report
from .json_exporter import generate_json_report
from .ai_pdf_generator import generate_ai_pdf_report
from analysis.ai_detector import AIDetectionEngine


@login_required
def report_detail_view(request, report_id):
    """View a similarity report."""
    report = get_object_or_404(
        SimilarityReport.objects.select_related('document', 'document__uploaded_by'),
        id=report_id
    )

    if not _can_view_report(request.user, report):
        return HttpResponseForbidden("You don't have permission to view this report.")

    # Log report view
    AuditLog.objects.create(
        user=request.user,
        action=AuditLog.Action.REPORT_VIEW,
        resource_type='SimilarityReport',
        resource_id=str(report_id),
        ip_address=_get_client_ip(request),
    )

    # Get matched passages grouped by source
    passages = report.matched_passages.filter(
        is_excluded=False
    ).select_related('source').order_by('submitted_page', 'submitted_char_start')

    excluded_passages = report.matched_passages.filter(
        is_excluded=True
    ).select_related('source')

    # Source breakdown
    source_groups = {}
    for p in passages:
        src_name = p.source.title if p.source else 'Unknown Source'
        if src_name not in source_groups:
            source_groups[src_name] = {
                'passages': [],
                'total_words': 0,
                'index': p.source_index,
                'source': p.source,
            }
        source_groups[src_name]['passages'].append(p)
        source_groups[src_name]['total_words'] += p.word_count

    from .criteria import compute_report_criteria
    criteria = compute_report_criteria(report)

    return render(request, 'reports/detail.html', {
        'report': report,
        'criteria': criteria,
        'passages': passages,
        'excluded_passages': excluded_passages,
        'source_groups': source_groups,
    })


@login_required
def report_list_view(request):
    """List similarity reports."""
    if request.user.is_admin:
        reports = SimilarityReport.objects.all()
    elif request.user.is_teacher:
        from django.db.models import Q
        reports = SimilarityReport.objects.filter(
            Q(created_by=request.user) |
            Q(document__uploaded_by=request.user) |
            Q(document__assignment__created_by=request.user)
        ).distinct()
    else:
        reports = SimilarityReport.objects.filter(
            document__uploaded_by=request.user
        )

    reports = reports.select_related('document', 'document__uploaded_by').order_by('-created_at')

    paginator = Paginator(reports, 15)
    page = request.GET.get('page', 1)
    reports_page = paginator.get_page(page)

    return render(request, 'reports/list.html', {
        'reports': reports_page,
    })


@login_required
def download_pdf_view(request, report_id):
    """Download report as PDF."""
    report = get_object_or_404(SimilarityReport, id=report_id)
    if not _can_view_report(request.user, report):
        return HttpResponseForbidden()

    AuditLog.objects.create(
        user=request.user,
        action=AuditLog.Action.REPORT_DOWNLOAD,
        resource_type='SimilarityReport',
        resource_id=str(report_id),
        details={'format': 'pdf'},
        ip_address=_get_client_ip(request),
    )

    pdf_buffer = generate_pdf_report(report)
    filename = f"similarity_report_{str(report.id)[:8]}.pdf"

    response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def download_docx_view(request, report_id):
    """Download report as DOCX."""
    report = get_object_or_404(SimilarityReport, id=report_id)
    if not _can_view_report(request.user, report):
        return HttpResponseForbidden()

    AuditLog.objects.create(
        user=request.user,
        action=AuditLog.Action.REPORT_DOWNLOAD,
        resource_type='SimilarityReport',
        resource_id=str(report_id),
        details={'format': 'docx'},
        ip_address=_get_client_ip(request),
    )

    docx_buffer = generate_docx_report(report)
    filename = f"similarity_report_{str(report.id)[:8]}.docx"

    response = HttpResponse(
        docx_buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def download_json_view(request, report_id):
    """Download report as JSON."""
    report = get_object_or_404(SimilarityReport, id=report_id)
    if not _can_view_report(request.user, report):
        return HttpResponseForbidden()

    data = generate_json_report(report)
    filename = f"similarity_report_{str(report.id)[:8]}.json"

    response = HttpResponse(
        json.dumps(data, indent=2, default=str),
        content_type='application/json'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _can_view_report(user, report):
    """Check if user can view a report."""
    if user.is_admin:
        return True
    if report.document.uploaded_by == user:
        return True
    if report.created_by == user:
        return True
    if user.is_teacher and report.document.assignment:
        if report.document.assignment.created_by == user:
            return True
    return False


def _get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _can_view_document(user, document):
    """Check if user can view document analysis."""
    if user.is_admin:
        return True
    if document.uploaded_by == user:
        return True
    if user.is_teacher and document.assignment:
        if document.assignment.created_by == user:
            return True
    return False


@login_required
def ai_report_view(request, doc_id):
    """View Turnitin-style AI writing detection report for a document."""
    document = get_object_or_404(
        Document.objects.select_related('uploaded_by', 'assignment'),
        id=doc_id
    )

    if not _can_view_document(request.user, document):
        return HttpResponseForbidden("You don't have permission to view AI reports for this document.")

    reanalyze = request.GET.get('reanalyze') == '1'
    ai_report = None
    if not reanalyze:
        ai_report = AIReport.objects.filter(document=document, status=AIReport.Status.COMPLETED).order_by('-created_at').first()

    if not ai_report:
        engine = AIDetectionEngine()
        ai_report = engine.analyze_document(document, user=request.user)

    # Log view
    AuditLog.objects.create(
        user=request.user,
        action=AuditLog.Action.REPORT_VIEW,
        resource_type='AIReport',
        resource_id=str(ai_report.id),
        ip_address=_get_client_ip(request),
    )

    # Latest similarity report for navigation toggle
    similarity_report = document.similarity_reports.order_by('-created_at').first()

    context = {
        'ai_report': ai_report,
        'document': document,
        'similarity_report': similarity_report,
    }
    return render(request, 'reports/ai_report.html', context)


@login_required
def download_ai_pdf_view(request, ai_report_id):
    """Download official Turnitin-styled AI Writing Detection PDF report."""
    ai_report = get_object_or_404(
        AIReport.objects.select_related('document', 'document__uploaded_by', 'document__assignment'),
        id=ai_report_id
    )

    if not _can_view_document(request.user, ai_report.document):
        return HttpResponseForbidden("You don't have permission to download this AI report.")

    AuditLog.objects.create(
        user=request.user,
        action=AuditLog.Action.REPORT_DOWNLOAD,
        resource_type='AIReport',
        resource_id=str(ai_report_id),
        details={'format': 'ai_pdf'},
        ip_address=_get_client_ip(request),
    )

    pdf_buffer = generate_ai_pdf_report(ai_report)
    safe_title = "".join(c for c in ai_report.document.title if c.isalnum() or c in (' ', '-', '_')).strip()[:35]
    filename = f"turnitin_ai_report_{safe_title}_{str(ai_report.id)[:8]}.pdf"

    response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

