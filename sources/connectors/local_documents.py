"""
Local Documents & Institutional Repository Connector.
Compares against active uploaded student submissions, institutional collections, and faculty libraries.
"""
import logging
from typing import List
from django.db.models import Q
from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class LocalDocumentConnector(BaseSourceConnector):
    """Connector for previously uploaded documents within the platform."""

    @property
    def id(self) -> str:
        return 'local_documents'

    @property
    def name(self) -> str:
        return 'Local Submissions & Institutional Repository'

    @property
    def source_type(self) -> str:
        return 'institutional'

    @property
    def description(self) -> str:
        return (
            "Compares against internal institution submissions, student papers, faculty reference collections, "
            "and archived manuscripts stored securely on this platform."
        )

    def is_available(self) -> bool:
        return True

    def search(self, query_text: str, max_results: int = 10, exclude_document_id: str = None, target_document=None) -> List[SourceProviderResult]:
        from documents.models import ReferenceSource, Document

        if not query_text or len(query_text.strip()) < 4:
            return []

        # Find matching ReferenceSources in DB
        words = [w for w in query_text.split() if len(w) > 3][:6]
        q_obj = Q()
        for w in words:
            q_obj |= Q(title__icontains=w) | Q(retrieved_text__icontains=w)

        qs = ReferenceSource.objects.filter(is_active=True)

        # Exclude current document ID to prevent self-comparison
        target_id = exclude_document_id or (getattr(target_document, 'id', None))
        if target_id:
            target_str = str(target_id)
            qs = qs.exclude(document_id=target_id).exclude(url__icontains=target_str)
            if target_document and getattr(target_document, 'title', None):
                target_title = target_document.title.strip().lower()
                qs = qs.exclude(source_type=ReferenceSource.SourceType.UPLOADED, title__iexact=target_title)

        refs = qs.filter(q_obj)[:max_results]
        results = []

        for r in refs:
            results.append(SourceProviderResult(
                title=r.title,
                author=r.author,
                publication_date=r.publication_date,
                url=r.url,
                doi=r.doi,
                text=r.retrieved_text,
                source_type=r.source_type,
                provider_name='Institutional Repository',
                access_limitations=r.access_limitations or 'Internal Institutional Access Only',
            ))

        return results

    def get_rate_limit_info(self) -> dict:
        return {
            'rate_limit': 'Unlimited local database lookups',
            'terms_url': '',
            'license_info': 'Private Institutional Academic Repository',
        }
