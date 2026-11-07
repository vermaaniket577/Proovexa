"""
Plagiarism Detection & Top Sources Aggregation Engine Package.
"""

from .ingestion import DocumentParser, ParsedDocument, TokenSpan, ParagraphSpan
from .preprocessor import BilingualPreprocessor
from .fingerprinting import (
    WinnowingFingerprinter,
    InvertedCorpusIndex,
    Fingerprint,
    RawMatch,
    SourceOccurrence,
    KarpRabinRollingHasher,
)
from .exclusions import ExclusionFiltersEngine, ExcludedRegion
from .top_sources import TopSourcesResolver, TopSourceItem, AnnotatedDocumentSpan
from .reporting import PlagiarismReportGenerator
from .engine import PlagiarismDetectionEngine

__all__ = [
    "PlagiarismDetectionEngine",
    "DocumentParser",
    "ParsedDocument",
    "TokenSpan",
    "ParagraphSpan",
    "BilingualPreprocessor",
    "WinnowingFingerprinter",
    "InvertedCorpusIndex",
    "Fingerprint",
    "RawMatch",
    "SourceOccurrence",
    "KarpRabinRollingHasher",
    "ExclusionFiltersEngine",
    "ExcludedRegion",
    "TopSourcesResolver",
    "TopSourceItem",
    "AnnotatedDocumentSpan",
    "PlagiarismReportGenerator",
]
