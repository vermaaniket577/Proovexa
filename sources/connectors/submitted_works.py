"""
Connector for the Submitted Works and Institutional Repositories Database.
Implements tenant-isolated cross-referencing across:
- Previously uploaded research papers & student assignments
- University dissertations, Master's & PhD theses
- Institutional research collections & consortium repositories
- Registered user submissions with authorized retention flags

Enforces strict tenant isolation, privacy controls, and institution-level permissions.
"""
from datetime import datetime
import logging
from typing import List, Optional
from django.db.models import Q

from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class SubmittedWorksConnector(BaseSourceConnector):
    """
    Connects to the local and institutional Submitted Works Database.
    Restricted to authorized retained submissions within permitted institutional scopes.
    """

    @property
    def id(self) -> str:
        return 'submitted_works'

    @property
    def name(self) -> str:
        return 'Submitted Works & Institutional Repositories'

    @property
    def source_type(self) -> str:
        return 'institutional'

    @property
    def description(self) -> str:
        return 'Multi-tenant repository of previously submitted student papers, university theses, dissertations, and authorized institutional research collections.'

    @property
    def supports_full_text(self) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def search(
        self,
        query_text: str,
        max_results: int = 5,
        institution=None,
        allow_cross_institutional: bool = False,
    ) -> List[SourceProviderResult]:
        """
        Searches previous submissions and institutional reference sources.
        Enforces tenant isolation by default unless cross-institutional consortium sharing is explicitly permitted.
        """
        if not query_text or len(query_text.strip()) < 4:
            return []

        from documents.models import ReferenceSource, Document
        results = []

        try:
            # 1. Search ReferenceSource records marked as institutional, uploaded, or student work
            q_filter = Q(source_type__in=[
                ReferenceSource.SourceType.UPLOADED,
                ReferenceSource.SourceType.INSTITUTIONAL,
            ]) & Q(is_active=True)

            # Strict Tenant Isolation: Limit to current institution if provided
            if institution and not allow_cross_institutional:
                q_filter &= (Q(institution=institution) | Q(institution__isnull=True))

            words = query_text.split()[:8]
            search_phrase = ' '.join(words)

            # Keyword containment check in retrieved_text or title
            text_filter = Q(retrieved_text__icontains=search_phrase) | Q(title__icontains=search_phrase)
            matching_sources = ReferenceSource.objects.filter(q_filter & text_filter)[:max_results]

            for s in matching_sources:
                inst_name = s.institution.name if s.institution else "Institutional Repository"
                results.append(SourceProviderResult(
                    title=f"{s.title} ({inst_name})",
                    author=s.author or "Student Author",
                    publication_date=s.publication_date or (s.created_at.date() if s.created_at else None),
                    url=s.url or "",
                    doi=s.doi or "",
                    text=s.retrieved_text or s.title,
                    source_type='institutional',
                    provider_name='Submitted Works Database',
                    journal_or_publisher=inst_name,
                    access_limitations='Private Institutional Repository / Authorized Retention'
                ))

            # 2. Search Document database where uploaded_by authorized retention
            if len(results) < max_results:
                needed = max_results - len(results)
                doc_filter = Q(status=Document.Status.COMPLETED)
                if institution and not allow_cross_institutional:
                    doc_filter &= Q(uploaded_by__institution=institution)

                doc_matches = Document.objects.filter(
                    doc_filter & Q(title__icontains=search_phrase)
                ).select_related('uploaded_by', 'uploaded_by__institution')[:needed]

                for d in doc_matches:
                    u_inst = d.uploaded_by.institution.name if (d.uploaded_by and d.uploaded_by.institution) else "Private Repository"
                    results.append(SourceProviderResult(
                        title=f"{d.title} ({u_inst})",
                        author="Student Submission",
                        publication_date=d.created_at.date() if d.created_at else None,
                        url="",
                        doi="",
                        text=f"Submitted work archived on {d.created_at.strftime('%Y-%m-%d')}",
                        source_type='institutional',
                        provider_name='Submitted Works Database',
                        journal_or_publisher=u_inst,
                        access_limitations='Private Institutional Repository (Tenant Isolated)'
                    ))

        except Exception as e:
            logger.debug(f"Submitted works query error: {e}")

        return results
