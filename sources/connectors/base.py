"""
Base source connector interface and standardized result container.
"""
from abc import ABC, abstractmethod
from datetime import datetime
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class SourceProviderResult:
    """Standardized result from an external or internal source provider."""

    def __init__(
        self,
        title: str = '',
        author: str = '',
        publication_date=None,
        url: str = '',
        doi: str = '',
        text: str = '',
        source_type: str = 'academic',
        provider_name: str = '',
        retrieval_timestamp: Optional[datetime] = None,
        matching_passage: str = '',
        access_limitations: str = '',
        journal_or_publisher: str = '',
        raw_metadata: Optional[Dict[str, Any]] = None,
    ):
        self.title = (title or '').strip()
        self.author = (author or '').strip()
        self.publication_date = publication_date
        self.url = (url or '').strip()
        self.doi = (doi or '').strip()
        self.text = (text or '').strip()
        self.source_type = source_type  # 'academic', 'open_access', 'web', 'institutional', 'uploaded'
        self.provider_name = provider_name
        self.retrieval_timestamp = retrieval_timestamp or datetime.utcnow()
        self.matching_passage = matching_passage
        self.access_limitations = access_limitations
        self.journal_or_publisher = journal_or_publisher
        self.raw_metadata = raw_metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            'title': self.title,
            'author': self.author,
            'publication_date': str(self.publication_date) if self.publication_date else None,
            'url': self.url,
            'doi': self.doi,
            'text': self.text,
            'source_type': self.source_type,
            'provider_name': self.provider_name,
            'retrieval_timestamp': str(self.retrieval_timestamp) if self.retrieval_timestamp else None,
            'matching_passage': self.matching_passage,
            'access_limitations': self.access_limitations,
            'journal_or_publisher': self.journal_or_publisher,
            'word_count': len(self.text.split()) if self.text else 0,
        }

    def to_reference_source(self, institution=None, document=None):
        """Converts or stores this result as a Django ReferenceSource model instance."""
        from documents.models import ReferenceSource
        from django.utils import timezone

        # Map connector source_type to ReferenceSource.SourceType
        type_mapping = {
            'academic': ReferenceSource.SourceType.ACADEMIC,
            'open_access': ReferenceSource.SourceType.OPEN_ACCESS,
            'web': ReferenceSource.SourceType.WEB,
            'institutional': ReferenceSource.SourceType.INSTITUTIONAL,
            'uploaded': ReferenceSource.SourceType.UPLOADED,
        }
        st = type_mapping.get(self.source_type, ReferenceSource.SourceType.ACADEMIC)

        pub_date = None
        if isinstance(self.publication_date, datetime):
            pub_date = self.publication_date.date()
        elif hasattr(self.publication_date, 'year'):
            pub_date = self.publication_date

        ref_source, _ = ReferenceSource.objects.get_or_create(
            url=self.url if self.url else (f"doi:{self.doi}" if self.doi else ""),
            defaults={
                'title': self.title[:500] if self.title else 'Untitled Source',
                'author': self.author[:500] if self.author else '',
                'source_type': st,
                'doi': self.doi[:100] if self.doi else '',
                'publication_date': pub_date,
                'retrieved_text': self.text,
                'word_count': len(self.text.split()) if self.text else 0,
                'retrieval_timestamp': timezone.now(),
                'access_limitations': self.access_limitations,
                'institution': institution,
                'document': document,
                'is_active': True,
            }
        )
        # Update text if it was previously empty and we now have retrieved text
        if self.text and (not ref_source.retrieved_text or len(ref_source.retrieved_text) < len(self.text)):
            ref_source.retrieved_text = self.text
            ref_source.word_count = len(self.text.split())
            ref_source.save(update_fields=['retrieved_text', 'word_count'])

        return ref_source


class BaseSourceConnector(ABC):
    """Abstract base class for all similarity source connectors."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique slug identifier for the provider (e.g. 'crossref')."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        pass

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Category: 'academic', 'open_access', 'web', 'institutional', 'uploaded'."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of the source provider and corpus covered."""
        pass

    @property
    def requires_api_key(self) -> bool:
        """Whether this provider requires an external API key."""
        return False

    @property
    def api_key_name(self) -> str:
        """Name of the environment variable holding the API key."""
        return ""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and ready for queries."""
        pass

    @abstractmethod
    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        """
        Search candidate publications or web sources for matching content.
        
        Args:
            query_text: Text snippet, phrase, or title to query
            max_results: Maximum records to retrieve
            
        Returns:
            List of SourceProviderResult instances
        """
        pass

    def test_connection(self) -> Dict[str, Any]:
        """
        Performs a live connectivity test for the admin dashboard.
        
        Returns:
            Dict: {'success': bool, 'message': str, 'latency_ms': float, 'count': int}
        """
        import time
        start = time.time()
        try:
            results = self.search("machine learning in healthcare", max_results=1)
            latency = round((time.time() - start) * 1000, 1)
            return {
                'success': True,
                'message': f"Connected successfully ({latency} ms, {len(results)} item retrieved)",
                'latency_ms': latency,
                'count': len(results),
            }
        except Exception as e:
            latency = round((time.time() - start) * 1000, 1)
            return {
                'success': False,
                'message': f"Connection test failed: {str(e)}",
                'latency_ms': latency,
                'count': 0,
            }

    def get_rate_limit_info(self) -> Dict[str, Any]:
        """Returns rate limit and access terms metadata."""
        return {
            'rate_limit': 'Standard Public API limits',
            'terms_url': '',
            'license_info': 'Authorized Open Access & Metadata Discovery',
        }
