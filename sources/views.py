"""
Source provider admin dashboard and live connectivity testing views.
"""
import os
import time
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Count, Avg

from accounts.decorators import role_required
from documents.models import ReferenceSource
from analysis.models import SimilarityReport
from .connectors import get_all_connectors, get_connector


@login_required
@role_required(['admin'])
def source_providers_view(request):
    """Admin dashboard to monitor source availability, API errors, and performance."""
    connectors = get_all_connectors()

    # Database statistics
    total_sources = ReferenceSource.objects.filter(is_active=True).count()
    type_counts = dict(
        ReferenceSource.objects.filter(is_active=True)
        .values('source_type')
        .annotate(c=Count('id'))
        .values_list('source_type', 'c')
    )

    # Comparison performance stats
    recent_reports = SimilarityReport.objects.filter(status=SimilarityReport.Status.COMPLETED)[:100]
    avg_processing_time = recent_reports.aggregate(avg_t=Avg('processing_time_seconds')).get('avg_t') or 0.0
    failed_comparisons = SimilarityReport.objects.filter(status=SimilarityReport.Status.FAILED).count()
    total_comparisons = SimilarityReport.objects.count()

    # API Key Configuration status
    api_configs = [
        {
            'name': 'Crossref Polite Pool Email',
            'env_var': 'CROSSREF_MAILTO',
            'is_set': bool(getattr(settings, 'CROSSREF_MAILTO', os.environ.get('CROSSREF_MAILTO', ''))),
            'current': getattr(settings, 'CROSSREF_MAILTO', os.environ.get('CROSSREF_MAILTO', 'admin@proovexa.edu')),
            'required': False,
            'description': 'Enables polite high-speed queue (50 req/s) with Crossref metadata API.',
        },
        {
            'name': 'OpenAlex Polite Email',
            'env_var': 'OPENALEX_MAILTO',
            'is_set': bool(getattr(settings, 'OPENALEX_MAILTO', os.environ.get('OPENALEX_MAILTO', ''))),
            'current': getattr(settings, 'OPENALEX_MAILTO', os.environ.get('OPENALEX_MAILTO', 'admin@proovexa.edu')),
            'required': False,
            'description': 'Identifies application for fast 100k queries/day rate limit with OpenAlex graph.',
        },
        {
            'name': 'Semantic Scholar API Key',
            'env_var': 'SEMANTIC_SCHOLAR_API_KEY',
            'is_set': bool(getattr(settings, 'SEMANTIC_SCHOLAR_API_KEY', os.environ.get('SEMANTIC_SCHOLAR_API_KEY', ''))),
            'current': 'configured (hidden)' if getattr(settings, 'SEMANTIC_SCHOLAR_API_KEY', os.environ.get('SEMANTIC_SCHOLAR_API_KEY', '')) else 'Not set',
            'required': False,
            'description': 'Eliminates 429 rate limiting for Allen Institute Semantic Scholar graph queries.',
        },
        {
            'name': 'CORE Research API Key',
            'env_var': 'CORE_API_KEY',
            'is_set': bool(getattr(settings, 'CORE_API_KEY', os.environ.get('CORE_API_KEY', ''))),
            'current': 'configured (hidden)' if getattr(settings, 'CORE_API_KEY', os.environ.get('CORE_API_KEY', '')) else 'Not set',
            'required': True,
            'description': 'Required to access CORE collection of 250M+ open access papers.',
        },
        {
            'name': 'Unpaywall Email Identifier',
            'env_var': 'UNPAYWALL_EMAIL',
            'is_set': bool(getattr(settings, 'UNPAYWALL_EMAIL', os.environ.get('UNPAYWALL_EMAIL', ''))),
            'current': getattr(settings, 'UNPAYWALL_EMAIL', os.environ.get('UNPAYWALL_EMAIL', 'admin@proovexa.edu')),
            'required': False,
            'description': 'Parameters sent to Unpaywall for finding legal open-access full-text PDFs by DOI.',
        },
        {
            'name': 'Google Custom Search API Key & CX',
            'env_var': 'GOOGLE_SEARCH_API_KEY / GOOGLE_SEARCH_CX',
            'is_set': bool(getattr(settings, 'GOOGLE_SEARCH_API_KEY', os.environ.get('GOOGLE_SEARCH_API_KEY', ''))),
            'current': 'configured' if getattr(settings, 'GOOGLE_SEARCH_API_KEY', os.environ.get('GOOGLE_SEARCH_API_KEY', '')) else 'Not set (using DuckDuckGo & Wikipedia)',
            'required': False,
            'description': 'Optional Google Custom Search API for deep web retrieval across educational domains.',
        },
    ]

    return render(request, 'sources/providers.html', {
        'connectors': connectors,
        'total_sources': total_sources,
        'type_counts': type_counts,
        'avg_processing_time': round(avg_processing_time, 2),
        'failed_comparisons': failed_comparisons,
        'total_comparisons': total_comparisons,
        'api_configs': api_configs,
    })


@login_required
@role_required(['admin'])
def test_connector_api_view(request, connector_id):
    """AJAX endpoint for testing individual source connector health and latency."""
    connector = get_connector(connector_id)
    if not connector:
        return JsonResponse({'success': False, 'message': f'Connector {connector_id} not found'}, status=404)

    test_res = connector.test_connection()
    return JsonResponse(test_res)
