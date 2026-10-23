"""
Analysis views: trigger analysis, view reports, configure exclusions.
"""
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.core.paginator import Paginator

from .models import SimilarityReport, MatchedPassage, ExclusionRule
from .engine import AnalysisEngine
from documents.models import Document
from accounts.models import AuditLog
from accounts.decorators import role_required


@login_required
def start_analysis_view(request, doc_id):
    """Start similarity analysis for a document."""
    document = get_object_or_404(Document, id=doc_id, is_deleted=False)

    # Authorization
    if document.uploaded_by != request.user and not request.user.is_admin and not request.user.is_teacher:
        return HttpResponseForbidden("You don't have permission to analyze this document.")

    if document.status not in [Document.Status.EXTRACTED, Document.Status.COMPLETED]:
        messages.error(request, 'Document text must be extracted before analysis can begin.')
        return redirect('documents:detail', doc_id=doc_id)

    if request.method == 'POST':
        # Get exclusion settings from form
        exclusion_settings = {
            'exclude_bibliography': request.POST.get('exclude_bibliography') == 'on',
            'exclude_quotations': request.POST.get('exclude_quotations') == 'on',
            'exclude_citations': request.POST.get('exclude_citations') == 'on',
            'min_match_words': int(request.POST.get('min_match_words', 5)),
            'exclude_common_phrases': request.POST.get('exclude_common_phrases') == 'on',
            'common_phrases_list': request.POST.get('common_phrases', '').strip().split('\n'),
            'exclude_sources': request.POST.getlist('exclude_sources'),
            'exclude_self_match': request.POST.get('exclude_self_match') == 'on',
        }

        # Run analysis
        engine = AnalysisEngine(exclusion_settings=exclusion_settings)
        report = engine.analyze_document(document, user=request.user)

        # Audit log
        AuditLog.objects.create(
            user=request.user,
            action=AuditLog.Action.ANALYZE,
            resource_type='Document',
            resource_id=str(doc_id),
            details={'report_id': str(report.id)},
            ip_address=_get_client_ip(request),
        )

        if report.status == SimilarityReport.Status.COMPLETED:
            messages.success(
                request,
                f'Analysis complete! Similarity: {report.overall_similarity:.1f}% '
                f'({report.source_count} sources found)'
            )
            return redirect('reports:detail', report_id=report.id)
        else:
            messages.error(request, f'Analysis failed: {report.error_message}')
            return redirect('documents:detail', doc_id=doc_id)

    # GET: show analysis configuration form
    exclusion_rules = ExclusionRule.objects.filter(is_enabled=True)

    return render(request, 'analysis/configure.html', {
        'document': document,
        'exclusion_rules': exclusion_rules,
    })


@login_required
def analysis_status_view(request, doc_id):
    """Check analysis status (for AJAX polling)."""
    document = get_object_or_404(Document, id=doc_id)
    latest_report = SimilarityReport.objects.filter(document=document).order_by('-created_at').first()

    data = {
        'document_status': document.status,
        'document_title': document.title,
    }

    if latest_report:
        data.update({
            'report_id': str(latest_report.id),
            'report_status': latest_report.status,
            'overall_similarity': latest_report.overall_similarity,
        })

    return JsonResponse(data)


@login_required
def quick_scan_view(request, doc_id):
    """
    1-Click report generation for a document.
    Generates both similarity and AI reports (or one of them if specified).
    """
    from .services import generate_both_reports, generate_similarity_report, generate_ai_report

    document = get_object_or_404(Document, id=doc_id, is_deleted=False)

    # Authorization
    if document.uploaded_by != request.user and not request.user.is_admin and not request.user.is_teacher:
        return HttpResponseForbidden("You don't have permission to scan this document.")

    scan_type = request.GET.get('type') or request.POST.get('type') or 'both'
    next_url = request.GET.get('next') or request.POST.get('next')

    try:
        if scan_type == 'similarity':
            sim_report = generate_similarity_report(document, user=request.user)
            messages.success(
                request,
                f"1-Click Similarity Scan complete for '{document.title}'! Score: {sim_report.similarity_display}"
            )
            if next_url:
                return redirect(next_url)
            return redirect('reports:detail', report_id=sim_report.id)

        elif scan_type == 'ai':
            ai_report = generate_ai_report(document, user=request.user)
            messages.success(
                request,
                f"1-Click AI Detection Scan complete for '{document.title}'! Score: {ai_report.overall_ai_score:.0f}% AI"
            )
            if next_url:
                return redirect(next_url)
            return redirect('reports:ai_report', doc_id=document.id)

        else:
            # Both reports in 1 click!
            sim_report, ai_report = generate_both_reports(document, user=request.user)
            messages.success(
                request,
                f"1-Click Scan complete for '{document.title}'! "
                f"Similarity: {sim_report.similarity_display} &bull; AI Content: {ai_report.overall_ai_score:.0f}%"
            )
            if next_url:
                return redirect(next_url)
            return redirect('reports:detail', report_id=sim_report.id)

    except Exception as e:
        messages.error(request, f"Report generation failed: {str(e)}")
        if next_url:
            return redirect(next_url)
        return redirect('documents:detail', doc_id=doc_id)


@login_required
@role_required(['admin'])
def exclusion_rules_view(request):
    """Admin: manage exclusion rules."""
    rules = ExclusionRule.objects.all()
    return render(request, 'analysis/exclusion_rules.html', {'rules': rules})


def _get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')
