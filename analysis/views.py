"""
Analysis views: trigger analysis, view reports, configure exclusions.
"""
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.core.paginator import Paginator

from .models import SimilarityReport, MatchedPassage, ExclusionRule, AIAPISettings
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
        from .services import ensure_document_extracted
        ok, err = ensure_document_extracted(document)
        if not ok:
            messages.error(request, f'Document text extraction required: {err}')
            return redirect('documents:detail', doc_id=doc_id)

    if request.method == 'POST':
        # Get exclusion settings from form
        exclusion_settings = {
            'exclude_bibliography': request.POST.get('exclude_bibliography') == 'on',
            'exclude_quotations': request.POST.get('exclude_quotations') == 'on',
            'exclude_citations': request.POST.get('exclude_citations') == 'on',
            'min_match_words': int(request.POST.get('min_match_words', 14)),
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
                f"Similarity: {sim_report.similarity_display} • AI Content: {ai_report.overall_ai_score:.0f}%"
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


@login_required
def api_ai_analyze_view(request):
    """
    REST API endpoint for real-time AI writing detection analysis.
    Accepts: JSON payload with 'text' or 'doc_id'.
    Returns: Calibrated metrics, segment-level classifications, confidence, and disclaimers.
    """
    import json
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except Exception:
        data = request.POST

    from .ai_detector import AIDetectionEngine
    engine = AIDetectionEngine()

    doc_id = data.get('doc_id')
    raw_text = data.get('text', '')

    if doc_id:
        document = get_object_or_404(Document, id=doc_id, is_deleted=False)
        if document.uploaded_by != request.user and not request.user.is_admin and not request.user.is_teacher:
            return JsonResponse({'error': 'Permission denied'}, status=403)
        ai_report = engine.analyze_document(document, user=request.user)
        return JsonResponse({
            'document_id': str(document.id),
            'document_title': document.title,
            'report_id': str(ai_report.id),
            'overall_ai_score': ai_report.overall_ai_score,
            'is_below_threshold': ai_report.overall_ai_score == 0.0,
            'display_score': ai_report.display_score,
            'model_version': ai_report.model_version,
            'model_confidence': ai_report.model_confidence,
            'uncertain_percentage': ai_report.uncertain_percentage,
            'ai_sentence_count': ai_report.ai_sentence_count,
            'total_sentences': ai_report.total_sentences,
            'linguistic_features': ai_report.linguistic_features,
            'segments': ai_report.segments_data,
            'limitations': ai_report.limitations,
        })

    if not raw_text.strip():
        return JsonResponse({'error': 'Parameter "text" or "doc_id" is required'}, status=400)

    result = engine.evaluate_text_snippet(raw_text)
    return JsonResponse(result)


@login_required
@role_required(['admin'])
def ai_settings_view(request):
    """
    Admin control panel to configure external AI API settings dynamically.
    Controls Gemini & OpenAI keys, model selections, parameters, and feature toggles.
    """
    ai_settings = AIAPISettings.get_settings()

    if request.method == 'POST':
        try:
            # Master toggles
            ai_settings.is_enabled = 'is_enabled' in request.POST
            ai_settings.provider = request.POST.get('provider', 'auto').strip().lower()

            # Gemini settings
            new_gemini_key = request.POST.get('gemini_api_key', '').strip()
            clear_gemini = request.POST.get('clear_gemini_key') == '1'
            if clear_gemini:
                ai_settings.gemini_api_key = ''
            elif new_gemini_key and not new_gemini_key.startswith('•'):
                ai_settings.gemini_api_key = new_gemini_key

            gemini_model = request.POST.get('gemini_model', '').strip()
            custom_gemini_model = request.POST.get('custom_gemini_model', '').strip()
            ai_settings.gemini_model = custom_gemini_model or gemini_model or 'gemini-1.5-flash'

            # OpenAI settings
            new_openai_key = request.POST.get('openai_api_key', '').strip()
            clear_openai = request.POST.get('clear_openai_key') == '1'
            if clear_openai:
                ai_settings.openai_api_key = ''
            elif new_openai_key and not new_openai_key.startswith('•'):
                ai_settings.openai_api_key = new_openai_key

            openai_model = request.POST.get('openai_model', '').strip()
            custom_openai_model = request.POST.get('custom_openai_model', '').strip()
            ai_settings.openai_model = custom_openai_model or openai_model or 'gpt-4o-mini'

            # Parameters & Limits
            try:
                ai_settings.timeout_seconds = max(5, min(120, int(request.POST.get('timeout_seconds', 15))))
            except (ValueError, TypeError):
                ai_settings.timeout_seconds = 15

            try:
                ai_settings.temperature = max(0.0, min(1.0, float(request.POST.get('temperature', 0.1))))
            except (ValueError, TypeError):
                ai_settings.temperature = 0.1

            try:
                ai_settings.max_tokens = max(256, min(8192, int(request.POST.get('max_tokens', 2048))))
            except (ValueError, TypeError):
                ai_settings.max_tokens = 2048

            try:
                ai_settings.blend_weight = max(0.0, min(1.0, float(request.POST.get('blend_weight', 0.5))))
            except (ValueError, TypeError):
                ai_settings.blend_weight = 0.5

            # Feature Toggles
            ai_settings.enable_ai_writing_detection = 'enable_ai_writing_detection' in request.POST
            ai_settings.enable_paraphrase_detection = 'enable_paraphrase_detection' in request.POST

            # Audit Metadata
            ai_settings.updated_by = request.user
            ai_settings.save()

            # Record Audit Trail
            try:
                AuditLog.objects.create(
                    user=request.user,
                    action=AuditLog.Action.SETTINGS_CHANGE,
                    resource_type='AIAPISettings',
                    resource_id=str(ai_settings.id),
                    details={
                        'provider': ai_settings.provider,
                        'is_enabled': ai_settings.is_enabled,
                        'gemini_model': ai_settings.gemini_model,
                        'openai_model': ai_settings.openai_model,
                        'enable_ai_writing': ai_settings.enable_ai_writing_detection,
                        'enable_paraphrase': ai_settings.enable_paraphrase_detection,
                    },
                    ip_address=_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                )
            except Exception:
                pass

            messages.success(request, "AI API and Engine settings updated successfully! Changes take effect immediately.")
            return redirect('analysis:ai_settings')

        except Exception as e:
            messages.error(request, f"Failed to save AI API settings: {str(e)}")

    context = {
        'settings': ai_settings,
        'gemini_masked_key': ai_settings.masked_gemini_key(),
        'openai_masked_key': ai_settings.masked_openai_key(),
        'has_gemini_key': bool(ai_settings.gemini_api_key),
        'has_openai_key': bool(ai_settings.openai_api_key),
        'recommended_gemini_models': [
            {'id': 'gemini-2.5-flash', 'name': 'Gemini 2.5 Flash (Recommended: Fast & High Throughput)'},
            {'id': 'gemini-flash-latest', 'name': 'Gemini Flash Latest (Auto-Updating)'},
            {'id': 'gemini-2.5-pro', 'name': 'Gemini 2.5 Pro (Deep Forensic Reasoning)'},
        ],
        'recommended_openai_models': [
            {'id': 'gpt-4o-mini', 'name': 'GPT-4o Mini (Recommended: Fast & Cost-Efficient)'},
            {'id': 'gpt-4o', 'name': 'GPT-4o (Flagship Multimodal & Forensic Accuracy)'},
            {'id': 'gpt-4-turbo', 'name': 'GPT-4 Turbo (High Precision)'},
            {'id': 'o3-mini', 'name': 'o3-mini (Reasoning Focused Engine)'},
        ],
    }
    return render(request, 'analysis/ai_settings.html', context)


@login_required
@role_required(['admin'])
def api_test_ai_connection_view(request):
    """
    AJAX endpoint to test AI API credentials and connectivity in real time.
    Supports testing unsaved keys directly from form inputs.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except Exception:
        data = request.POST

    provider = data.get('provider', 'gemini').lower()
    input_key = (data.get('api_key') or '').strip()
    input_model = (data.get('model') or '').strip()

    # If the user left key blank or it's masked, fall back to stored DB key
    ai_settings = AIAPISettings.get_settings()
    if not input_key or input_key.startswith('•'):
        if provider == 'gemini':
            input_key = ai_settings.gemini_api_key
        elif provider == 'openai':
            input_key = ai_settings.openai_api_key

    from .ai_api_client import AIAPIClient
    client = AIAPIClient(ai_settings=ai_settings)
    result = client.test_connection(provider=provider, api_key=input_key, model=input_model)

    return JsonResponse(result)


