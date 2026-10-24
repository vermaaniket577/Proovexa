"""
Core Academic Text Similarity Scoring Engine.
Implements word-level position tracking, deduplication, and exclusion filtering.

Mathematical Formula:
=====================
E = Eligible words in submitted document after active exclusions.
M = Unique eligible words covered by verified text-matching spans.

Similarity Percentage = ( |M ∩ E| / |E| ) × 100

Properties:
1. Overlapping spans across multiple sources are deduplicated at word position level.
2. Individual source percentages do not double-count overlapping passages.
3. Preserves both Unfiltered Similarity and Filtered Similarity simultaneously.
4. Distinguishes exact phrase matches, winnowed matches, near-duplicate matches, and semantic distance.
"""
import re
import logging
from typing import List, Dict, Any, Set, Tuple, Optional

logger = logging.getLogger(__name__)


class WordSpan:
    """Represents a range of word indices in the submitted document."""
    __slots__ = ('word_start', 'word_end', 'source_id', 'source_name', 'match_type', 'similarity')

    def __init__(self, word_start: int, word_end: int, source_id: Any = None,
                 source_name: str = '', match_type: str = 'exact', similarity: float = 1.0):
        self.word_start = word_start
        self.word_end = word_end
        self.source_id = source_id
        self.source_name = source_name
        self.match_type = match_type
        self.similarity = similarity

    @property
    def indices(self) -> Set[int]:
        """Set of discrete word indices covered by this span."""
        return set(range(self.word_start, self.word_end + 1))


class AcademicSimilarityScorer:
    """
    Computes explainable word-position similarity scores and non-overlapping source rankings.
    """

    def __init__(self, total_text_length: int = 0, total_word_count: int = 0, full_text: str = ""):
        # Handle cases where either word count or text length is passed
        if total_word_count == 0 and total_text_length > 0:
            total_word_count = max(1, total_text_length // 6)
        self.total_text_length = max(0, total_text_length)
        self.total_word_count = max(1, total_word_count)
        self.full_text = full_text
        self.all_word_positions: Set[int] = set(range(self.total_word_count))
        self.excluded_word_positions: Set[int] = set()

        self.match_spans: List[WordSpan] = []
        self.source_spans: Dict[Any, List[WordSpan]] = {}
        self.source_metadata: Dict[Any, Dict[str, Any]] = {}

        # Semantic similarity stored separately from textual overlap
        self.semantic_similarity_score: Optional[float] = None

    def add_exclusion_span(self, word_start: int, word_end: int):
        """Mark a range of word positions as excluded (e.g. bibliography, quote)."""
        if word_end < word_start:
            return
        for idx in range(max(0, word_start), min(self.total_word_count, word_end + 1)):
            self.excluded_word_positions.add(idx)

    def add_match_span(
        self,
        word_start: int,
        word_end: int,
        source_id: Any = None,
        source_name: str = '',
        source_category: str = 'Submitted Document',
        source_url: str = '',
        match_type: str = 'exact',
        similarity: float = 1.0
    ):
        """Register a verified text match span covering [word_start, word_end]."""
        if word_end < word_start or word_start < 0:
            return

        span = WordSpan(
            word_start=word_start,
            word_end=word_end,
            source_id=source_id,
            source_name=source_name,
            match_type=match_type,
            similarity=similarity
        )
        self.match_spans.append(span)

        if source_id is not None:
            if source_id not in self.source_spans:
                self.source_spans[source_id] = []
                self.source_metadata[source_id] = {
                    'title': source_name,
                    'category': source_category,
                    'url': source_url,
                }
            self.source_spans[source_id].append(span)

    def set_semantic_similarity(self, score: float):
        """Record separate semantic similarity metric (0.0 to 1.0)."""
        self.semantic_similarity_score = round(max(0.0, min(1.0, score)), 4)

    def set_source_hybrid_metrics(
        self,
        source_id: Any,
        composite_similarity_pct: float,
        exact_shingle_containment_pct: float,
        lexical_tfidf_pct: float,
        semantic_paraphrase_pct: float,
        exact_matched_shingles: Optional[List[str]] = None,
        flagged_sentences: Optional[List[Dict[str, Any]]] = None,
    ):
        """Record 3-tier hybrid evaluation metrics for a source."""
        if source_id not in self.source_metadata:
            self.source_metadata[source_id] = {
                'title': str(source_id),
                'category': 'Submitted Document',
                'url': '',
            }
        self.source_metadata[source_id].update({
            'composite_similarity_pct': composite_similarity_pct,
            'exact_shingle_containment_pct': exact_shingle_containment_pct,
            'lexical_tfidf_pct': lexical_tfidf_pct,
            'semantic_paraphrase_pct': semantic_paraphrase_pct,
            'exact_matched_shingles': exact_matched_shingles or [],
            'flagged_sentences': flagged_sentences or [],
        })

    def calculate(self) -> Dict[str, Any]:
        """
        Executes explainable score aggregation based on unique word sets.
        Returns comprehensive dictionary with overall, source-level, and exclusion breakdowns.
        """
        if self.total_word_count == 0:
            return self._empty_result()

        # E = Eligible word positions after exclusions
        eligible_set = self.all_word_positions - self.excluded_word_positions
        E_count = len(eligible_set)

        # M_all = All unique word positions covered by any match span
        M_all: Set[int] = set()
        M_exact: Set[int] = set()
        M_near: Set[int] = set()

        for span in self.match_spans:
            span_indices = span.indices
            M_all.update(span_indices)
            if span.match_type in ('exact', 'winnowing', 'phrase'):
                M_exact.update(span_indices)
            else:
                M_near.update(span_indices)

        # Unfiltered metrics (prior to applying exclusions)
        unfiltered_matched_words = len(M_all)
        unfiltered_similarity = round((unfiltered_matched_words / self.total_word_count) * 100, 2)

        # Filtered metrics (M ∩ E / E)
        if E_count == 0:
            filtered_matched_words = 0
            overall_similarity = 0.0
            status_text = "Not calculable (100% of document is excluded)"
        else:
            filtered_matched_words = len(M_all & eligible_set)
            exact_matched_words = len(M_exact & eligible_set)
            near_matched_words = len(M_near & eligible_set)

            overall_similarity = round((filtered_matched_words / E_count) * 100, 2)
            exact_similarity = round((exact_matched_words / E_count) * 100, 2)
            near_similarity = round((near_matched_words / E_count) * 100, 2)
            status_text = "Completed"

        # Calculate Source-Level Breakdown & Hierarchical Non-Overlapping Attribution
        source_rankings = self._compute_source_rankings(eligible_set, E_count)

        return {
            'overall_similarity': min(100.0, overall_similarity),
            'unfiltered_similarity': min(100.0, unfiltered_similarity),
            'exact_similarity': min(100.0, exact_similarity) if E_count > 0 else 0.0,
            'near_duplicate_similarity': min(100.0, near_similarity) if E_count > 0 else 0.0,
            'semantic_similarity': self.semantic_similarity_score,
            'total_words': self.total_word_count,
            'eligible_words': E_count,
            'excluded_words': len(self.excluded_word_positions),
            'matched_words': filtered_matched_words,
            'unfiltered_matched_words': unfiltered_matched_words,
            'source_count': len(self.source_spans),
            'status': status_text,
            'formula': "Similarity % = (Unique Eligible Matched Words / Total Eligible Words) × 100",
            'sources': source_rankings,
        }

    def _compute_source_rankings(self, eligible_set: Set[int], E_count: int) -> List[Dict[str, Any]]:
        """
        Calculates both Gross Overlap and Unique Non-Overlapping Contribution for each source.
        Sorts sources greedily by primary contribution so their non-overlapping percentages sum to overall %.
        """
        if E_count == 0 or not self.source_spans:
            return []

        # Step 1: Compute gross eligible words for each source
        source_gross_words: Dict[Any, Set[int]] = {}
        for source_id, spans in self.source_spans.items():
            s_set = set()
            for span in spans:
                s_set.update(span.indices)
            source_gross_words[source_id] = s_set & eligible_set

        # Step 2: Sort sources descending by gross matched words
        sorted_sources = sorted(
            source_gross_words.keys(),
            key=lambda sid: len(source_gross_words[sid]),
            reverse=True
        )

        # Step 3: Compute unique marginal contribution (preventing double-counting)
        covered_so_far: Set[int] = set()
        rankings = []

        for rank, sid in enumerate(sorted_sources, 1):
            gross_indices = source_gross_words[sid]
            gross_words = len(gross_indices)
            gross_pct = round((gross_words / E_count) * 100, 2)

            # Unique marginal words not covered by higher-ranked sources
            unique_indices = gross_indices - covered_so_far
            unique_words = len(unique_indices)
            unique_pct = round((unique_words / E_count) * 100, 2)

            covered_so_far.update(gross_indices)

            meta = self.source_metadata.get(sid, {})
            spans = self.source_spans[sid]

            exact_count = sum(1 for sp in spans if sp.match_type in ('exact', 'winnowing', 'phrase'))
            fuzzy_count = sum(1 for sp in spans if sp.match_type in ('fuzzy', 'near_duplicate'))

            rankings.append({
                'source_id': str(sid),
                'rank': rank,
                'title': meta.get('title', f"Source #{rank}"),
                'category': meta.get('category', 'Submitted Document'),
                'url': meta.get('url', ''),
                'gross_matched_words': gross_words,
                'gross_percentage': gross_pct,
                'unique_matched_words': unique_words,
                'unique_percentage': unique_pct,
                'exact_matches': exact_count,
                'near_duplicate_matches': fuzzy_count,
                'passage_count': len(spans),
                'composite_similarity_pct': meta.get('composite_similarity_pct', gross_pct),
                'exact_shingle_containment_pct': meta.get('exact_shingle_containment_pct', gross_pct),
                'lexical_tfidf_pct': meta.get('lexical_tfidf_pct', gross_pct),
                'semantic_paraphrase_pct': meta.get('semantic_paraphrase_pct', 0.0),
                'exact_matched_shingles': meta.get('exact_matched_shingles', []),
                'flagged_sentences': meta.get('flagged_sentences', []),
            })

        return rankings

    def _empty_result(self) -> Dict[str, Any]:
        return {
            'overall_similarity': 0.0,
            'unfiltered_similarity': 0.0,
            'exact_similarity': 0.0,
            'near_duplicate_similarity': 0.0,
            'semantic_similarity': None,
            'total_words': 0,
            'eligible_words': 0,
            'excluded_words': 0,
            'matched_words': 0,
            'unfiltered_matched_words': 0,
            'source_count': 0,
            'status': "Not calculable (Empty document)",
            'formula': "Similarity % = (Unique Eligible Matched Words / Total Eligible Words) × 100",
            'sources': [],
        }

    # Backward compatibility alias
    calculate_overall_similarity = calculate


# Backward compatibility class alias
SimilarityScorer = AcademicSimilarityScorer

