"""
Report views: view, download (PDF/DOCX/JSON), and list reports.
"""
import json
from datetime import datetime
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

    from analysis.services import ensure_report_passages
    ensure_report_passages(report)

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

    # Prepare document paragraphs with inline color-coded highlights matching Top Sources
    import html

    TURNITIN_PALETTE = [
        ('#e91e63', '#fce4ec', '#f48fb1'),  # 1: Magenta / Pink
        ('#1976d2', '#e3f2fd', '#90caf9'),  # 2: Blue
        ('#2e7d32', '#e8f5e9', '#a5d6a7'),  # 3: Green
        ('#7b1fa2', '#f3e5f5', '#ce93d8'),  # 4: Purple
        ('#c2185b', '#fce4ec', '#f48fb1'),  # 5: Rose
        ('#0288d1', '#e1f5fe', '#81d4fa'),  # 6: Sky Blue
        ('#00897b', '#e0f2f1', '#80cbc4'),  # 7: Teal
        ('#5e35b1', '#ede7f6', '#b39ddb'),  # 8: Deep Purple
        ('#d81b60', '#fce4ec', '#f48fb1'),  # 9: Magenta
        ('#0d47a1', '#e8eaf6', '#9fa8da'),  # 10: Dark Blue
        ('#ec407a', '#f8bbd0', '#f48fb1'),  # 11: Soft Pink
        ('#1565c0', '#bbdefb', '#90caf9'),  # 12: Royal Blue
        ('#00695c', '#b2dfdb', '#80cbc4'),  # 13: Pine
    ]

    extracted_texts = report.document.extracted_texts.all().order_by('page_number', 'paragraph_number')
    paragraphs_data = []

    for et in extracted_texts:
        raw_content = et.content
        escaped_html = html.escape(raw_content)

        # Check which matched passages belong to this paragraph
        para_matches = [
            p for p in passages 
            if p.submitted_text and p.submitted_text.strip() and (
                p.submitted_text.strip() in raw_content or 
                (p.submitted_paragraph == et.paragraph_number and p.submitted_page == et.page_number)
            )
        ]

        top_badge = None
        top_color = None

        if para_matches:
            sorted_matches = sorted(para_matches, key=lambda m: len(m.submitted_text), reverse=True)
            top_m = sorted_matches[0]
            top_badge = top_m.source_index or 1
            top_color, _, _ = TURNITIN_PALETTE[(top_badge - 1) % len(TURNITIN_PALETTE)]

            for m in sorted_matches:
                m_idx = m.source_index or 1
                solid_col, pastel_bg, border_col = TURNITIN_PALETTE[(m_idx - 1) % len(TURNITIN_PALETTE)]
                m_text = m.submitted_text.strip()
                m_escaped = html.escape(m_text)
                src_title = html.escape(m.source.title if m.source else "Reference Database")

                replacement = (
                    f'<mark class="turnitin-highlight source-match-{m_idx}" '
                    f'data-source-index="{m_idx}" data-source-title="{src_title}" '
                    f'style="background-color: {pastel_bg}; border-bottom: 2px solid {solid_col}; color: #0f172a; padding: 2px 4px; border-radius: 3px; position: relative; cursor: pointer;" '
                    f'title="Source [{m_idx}]: {src_title}">'
                    f'<span class="badge text-white me-1 align-text-top" style="background-color: {solid_col}; font-size: 0.72rem; padding: 2px 5px; border-radius: 3px;">{m_idx}</span>'
                    f'{m_escaped}'
                    f'</mark>'
                )

                if m_escaped in escaped_html:
                    escaped_html = escaped_html.replace(m_escaped, replacement, 1)

        paragraphs_data.append({
            'page_number': et.page_number,
            'paragraph_number': et.paragraph_number,
            'html': escaped_html,
            'top_badge': top_badge,
            'top_color': top_color,
            'has_match': bool(para_matches),
        })

    return render(request, 'reports/detail.html', {
        'report': report,
        'criteria': criteria,
        'passages': passages,
        'paragraphs_data': paragraphs_data,
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

    from analysis.services import ensure_report_passages
    ensure_report_passages(report)

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

    num_seed = abs(hash(str(ai_report.id))) % 900000000 + 100000000
    submission_id = f"trn:oid:::1:{num_seed}"

    uploaded_by = document.uploaded_by
    author_name = uploaded_by.get_full_name() or uploaded_by.username or "Student Author"
    inst_name = getattr(uploaded_by.institution, 'name', 'Academic Institute') if getattr(uploaded_by, 'institution', None) else 'Academic Institute'

    score = ai_report.overall_ai_score
    overall_ai_display = "*" if score == 0 else f"{score:.0f}%"

    file_size_display = "0 KB"
    if document.file_size:
        if document.file_size >= 1048576:
            file_size_display = f"{document.file_size / 1048576:.2f} MB"
        else:
            file_size_display = f"{document.file_size / 1024:.1f} KB"

    page_count = document.page_count or 1
    total_pages = page_count + 2  # Cover + Overview + Submission pages

    char_count = (document.word_count or 100) * 6
    if hasattr(document, 'extracted_texts') and document.extracted_texts.exists():
        char_count = sum(len(t.content) for t in document.extracted_texts.all())

    context = {
        'ai_report': ai_report,
        'document': document,
        'similarity_report': similarity_report,
        'author_name': author_name,
        'institution_name': inst_name,
        'submission_id': submission_id,
        'submission_date': (document.uploaded_at or ai_report.created_at).strftime('%b %d, %Y, %I:%M %p GMT+1'),
        'download_date': datetime.now().strftime('%b %d, %Y, %I:%M %p GMT+1'),
        'overall_ai_display': overall_ai_display,
        'file_size_display': file_size_display,
        'page_count': page_count,
        'word_count': document.word_count or 0,
        'character_count': char_count,
        'total_pages': total_pages,
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

