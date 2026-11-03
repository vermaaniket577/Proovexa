"""
Extensible source provider interface.
Bridged to modular academic and web connectors in sources.connectors.
"""
from typing import List
from .connectors.base import SourceProviderResult, BaseSourceConnector
from .connectors import (
    get_all_connectors,
    get_available_connectors,
    get_connector,
    multi_source_search,
    CrossrefConnector,
    OpenAlexConnector,
    ArxivConnector,
    EuropePMCConnector,
    PubMedCentralConnector,
    DOAJConnector,
    SemanticScholarConnector,
    COREConnector,
    UnpaywallConnector,
    WikipediaConnector,
    WebSearchConnector,
    LocalDocumentConnector,
    CodeSimilarityConnector,
)

# Backward-compatible aliases
BaseSourceProvider = BaseSourceConnector
LocalDocumentProvider = LocalDocumentConnector
InstitutionalCollectionProvider = LocalDocumentConnector
CrossrefProvider = CrossrefConnector
COREProvider = COREConnector


def get_available_providers() -> List[BaseSourceConnector]:
    """Return list of all configured and available source connectors."""
    return get_available_connectors()


def get_all_providers() -> List[BaseSourceConnector]:
    """Return list of all source connectors with real availability status."""
    return get_all_connectors()
