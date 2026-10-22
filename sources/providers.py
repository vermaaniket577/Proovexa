"""
Extensible source provider interface.
Each provider returns standardized results for comparison.
"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger(__name__)


class SourceProviderResult:
    """Standardized result from a source provider."""

    def __init__(self):
        self.title = ''
        self.author = ''
        self.publication_date = None
        self.url = ''
        self.doi = ''
        self.text = ''
        self.retrieval_timestamp = None
        self.matching_passage = ''
        self.access_limitations = ''

    def to_dict(self):
        return {
            'title': self.title,
            'author': self.author,
            'publication_date': str(self.publication_date) if self.publication_date else None,
            'url': self.url,
            'doi': self.doi,
            'text': self.text,
            'retrieval_timestamp': str(self.retrieval_timestamp) if self.retrieval_timestamp else None,
            'matching_passage': self.matching_passage,
            'access_limitations': self.access_limitations,
        }


class BaseSourceProvider(ABC):
    """Abstract base class for source providers."""

    @property
    @abstractmethod
    def name(self):
        """Provider name."""
        pass

    @property
    @abstractmethod
    def source_type(self):
        """Source type identifier."""
        pass

    @abstractmethod
    def search(self, query_text, max_results=10):
        """
        Search for matching content.
        
        Args:
            query_text: Text to search for
            max_results: Maximum number of results to return
        
        Returns:
            list of SourceProviderResult instances
        """
        pass

    @abstractmethod
    def is_available(self):
        """Check if this provider is configured and available."""
        pass


class LocalDocumentProvider(BaseSourceProvider):
    """Provider for locally uploaded documents."""

    @property
    def name(self):
        return 'Local Documents'

    @property
    def source_type(self):
        return 'uploaded'

    def search(self, query_text, max_results=10):
        """Search local documents - handled by the analysis engine directly."""
        return []

    def is_available(self):
        return True


class InstitutionalCollectionProvider(BaseSourceProvider):
    """Provider for institution's private reference collection."""

    @property
    def name(self):
        return 'Institutional Collection'

    @property
    def source_type(self):
        return 'institutional'

    def search(self, query_text, max_results=10):
        """Search institutional collection - handled by the analysis engine."""
        return []

    def is_available(self):
        return True


# Phase 3 providers (stubs)

class CrossrefProvider(BaseSourceProvider):
    """Provider for Crossref open metadata API (Phase 3)."""

    @property
    def name(self):
        return 'Crossref'

    @property
    def source_type(self):
        return 'academic'

    def search(self, query_text, max_results=10):
        logger.info("Crossref provider: not yet implemented (Phase 3)")
        return []

    def is_available(self):
        return False  # Not yet implemented


class COREProvider(BaseSourceProvider):
    """Provider for CORE open access API (Phase 3)."""

    @property
    def name(self):
        return 'CORE'

    @property
    def source_type(self):
        return 'open_access'

    def search(self, query_text, max_results=10):
        logger.info("CORE provider: not yet implemented (Phase 3)")
        return []

    def is_available(self):
        return False  # Not yet implemented


def get_available_providers():
    """Return list of all available source providers."""
    providers = [
        LocalDocumentProvider(),
        InstitutionalCollectionProvider(),
        CrossrefProvider(),
        COREProvider(),
    ]
    return [p for p in providers if p.is_available()]


def get_all_providers():
    """Return list of all source providers with availability status."""
    return [
        LocalDocumentProvider(),
        InstitutionalCollectionProvider(),
        CrossrefProvider(),
        COREProvider(),
    ]
