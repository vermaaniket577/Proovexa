"""
Unified Industrial Plagiarism Detection & "Top Sources" Aggregation Engine.
============================================================================
Production-ready engine supporting English and Hindi (Devanagari script),
modeled after industrial systems like Turnitin.

Pipeline Stages:
1. Dynamic Document Ingestion & Text Extraction (supports PDF, DOCX, TXT).
2. Bilingual Preprocessing & Normalization (English & Hindi).
3. Fingerprinting & Candidate Match Retrieval (Winnowing / Karp-Rabin k-grams).
4. Exclusion Filters Engine (Bibliography, Quoted text, Cited text).
5. Top Sources Overlap Resolution Algorithm (Greedy Set-Cover).
6. Similarity Metrics & Dynamic Report Generator (Turnitin-style payload).
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Union

from .ingestion import DocumentParser, ParsedDocument, TokenSpan
from .preprocessor import BilingualPreprocessor
from .fingerprinting import WinnowingFingerprinter, InvertedCorpusIndex, RawMatch
from .exclusions import ExclusionFiltersEngine, ExcludedRegion
from .top_sources import TopSourcesResolver, TopSourceItem, AnnotatedDocumentSpan
from .reporting import PlagiarismReportGenerator

logger = logging.getLogger(__name__)


class PlagiarismDetectionEngine:
    """
    Production-grade Plagiarism Detection & Top Sources Aggregation Engine.
    Fully supports English, Hindi (Devanagari), and mixed multilingual manuscripts.
    """

    def __init__(
        self,
        k_shingle_size: int = 7,
        window_size: int = 5,
        min_match_words: int = 8,
        exclude_bibliography: bool = True,
        exclude_quotations: bool = True,
        exclude_citations: bool = True,
    ):
        self.k = k_shingle_size
        self.w = window_size
        self.min_match_words = min_match_words

        self.preprocessor = BilingualPreprocessor()
        self.fingerprinter = WinnowingFingerprinter(k=self.k, w=self.w)
        self.inverted_index = InvertedCorpusIndex(fingerprinter=self.fingerprinter)
        self.exclusion_engine = ExclusionFiltersEngine(
            exclude_bibliography=exclude_bibliography,
            exclude_quotations=exclude_quotations,
            exclude_citations=exclude_citations,
            min_match_words=self.min_match_words,
        )
        self.top_sources_resolver = TopSourcesResolver(min_continuous_words=self.min_match_words)

    # -------------------------------------------------------------------------
    # Document Ingestion Helper
    # -------------------------------------------------------------------------
    def ingest_document(
        self,
        source: Union[str, Path, bytes],
        filename: Optional[str] = None,
        file_type: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> ParsedDocument:
        """Parses any supported document format (.pdf, .docx, .txt, bytes, string)."""
        return DocumentParser.parse(
            source=source,
            filename=filename,
            file_type=file_type,
            document_id=document_id,
        )

    # -------------------------------------------------------------------------
    # Corpus Indexing
    # -------------------------------------------------------------------------
    def index_source(
        self,
        source_id: str,
        source_name: str,
        text: str,
        source_type: str = "Internet",
        source_url: str = "",
    ):
        """Indexes a single reference source document into the inverted index."""
        tokens = self.preprocessor.tokenize_with_offsets(text)
        self.inverted_index.add_source(
            source_id=source_id,
            source_name=source_name,
            tokens=tokens,
            full_text=text,
            source_type=source_type,
            source_url=source_url,
        )

    def index_corpus(self, sources: List[Dict[str, Any]]):
        """
        Indexes an indexed database/corpus of sources (web crawl, publications, student papers).
        Each entry: {"id": str, "name": str (or "title"), "text": str, "type": str, "url": str}
        """
        for s in sources:
            sid = str(s.get("id") or s.get("source_id") or f"src_{len(self.inverted_index.sources) + 1}")
            sname = s.get("name") or s.get("title") or f"Source {sid}"
            stext = s.get("text") or s.get("content") or ""
            stype = s.get("type") or s.get("category") or s.get("source_type") or "Internet"
            surl = s.get("url") or s.get("source_url") or ""
            if stext.strip():
                self.index_source(
                    source_id=sid,
                    source_name=sname,
                    text=stext,
                    source_type=stype,
                    source_url=surl,
                )

    # -------------------------------------------------------------------------
    # Core End-to-End Analysis Pipeline
    # -------------------------------------------------------------------------
    def analyze(
        self,
        document: Union[str, Path, bytes, ParsedDocument],
        candidate_sources: Optional[List[Dict[str, Any]]] = None,
        exclusion_settings: Optional[Dict[str, bool]] = None,
        filename: Optional[str] = None,
        submission_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes the full 6-stage Plagiarism Detection and Top Sources Resolution Pipeline:
        1. Document Ingestion & Parsing
        2. Bilingual Preprocessing & Normalization
        3. Fingerprinting & Candidate Match Retrieval (Winnowing / Karp-Rabin k-grams)
        4. Exclusion Filters Engine (Bibliography, Quoted text, Cited text)
        5. Top Sources Overlap Resolution Algorithm (Greedy Set-Cover)
        6. Similarity Metrics & Dynamic Turnitin Report Generation
        """
        # Configure exclusions if custom settings passed
        if exclusion_settings:
            self.exclusion_engine.exclude_bibliography = exclusion_settings.get(
                "exclude_bibliography", self.exclusion_engine.exclude_bibliography
            )
            self.exclusion_engine.exclude_quotations = exclusion_settings.get(
                "exclude_quotations", self.exclusion_engine.exclude_quotations
            )
            self.exclusion_engine.exclude_citations = exclusion_settings.get(
                "exclude_citations", self.exclusion_engine.exclude_citations
            )

        # Stage 1: Ingestion
        if isinstance(document, ParsedDocument):
            parsed_doc = document
        else:
            parsed_doc = self.ingest_document(document, filename=filename, document_id=submission_id)

        # Index any ad-hoc candidate sources passed for this analysis
        if candidate_sources:
            self.index_corpus(candidate_sources)

        sub_text = parsed_doc.full_text
        sub_tokens = parsed_doc.tokens
        total_words = parsed_doc.word_count

        # Stage 4: Detect Excluded Regions (Bibliography, Quotations, Citations)
        exclusions = self.exclusion_engine.get_all_exclusions(sub_text)
        excluded_token_indices = self.exclusion_engine.get_excluded_token_indices(sub_tokens, exclusions)

        # Stage 3: Fingerprinting & Match Retrieval via Inverted Index
        raw_matches = self.inverted_index.query(
            sub_tokens=sub_tokens,
            sub_text=sub_text,
            min_match_words=self.min_match_words,
        )

        # Stage 5: Greedy Weighted Set Cover Top Sources Resolution
        top_sources, annotated_spans, claimed_tokens = self.top_sources_resolver.resolve(
            raw_matches=raw_matches,
            tokens=sub_tokens,
            full_text=sub_text,
            total_words=total_words,
            excluded_token_indices=excluded_token_indices,
            exclusion_engine=self.exclusion_engine,
        )

        # Stage 6: Report Generation matching industrial Turnitin schema
        report_payload = PlagiarismReportGenerator.build_report(
            parsed_doc=parsed_doc,
            top_sources=top_sources,
            annotated_spans=annotated_spans,
            claimed_tokens=claimed_tokens,
            exclusion_engine=self.exclusion_engine,
            submission_id=submission_id or parsed_doc.document_id,
        )

        return report_payload
