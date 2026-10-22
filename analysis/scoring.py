"""
Scoring module: calculates overall similarity without double-counting.
Provides a transparent, documented scoring formula.
"""
import logging

logger = logging.getLogger(__name__)


class SimilarityScorer:
    """
    Calculates the overall similarity score from individual match results.
    
    Scoring Formula:
    ================
    1. Collect all matched text spans from all comparison methods.
    2. Merge overlapping spans to avoid double-counting.
    3. Calculate matched character coverage: (total matched chars) / (total document chars).
    4. The overall similarity percentage = matched coverage × 100.
    
    This approach ensures:
    - No double-counting when multiple methods find the same passage.
    - The score represents actual text coverage, not an average of method scores.
    - Each source's contribution is tracked separately.
    """

    def __init__(self, total_text_length, total_word_count):
        self.total_text_length = max(total_text_length, 1)
        self.total_word_count = max(total_word_count, 1)
        self.all_spans = []  # List of (start, end, source_id, match_type)
        self.source_spans = {}  # source_id -> list of (start, end)

    def add_match_span(self, char_start, char_end, source_id=None, match_type='exact'):
        """Add a matched text span."""
        if char_end <= char_start:
            return
        self.all_spans.append((char_start, char_end, source_id, match_type))

        if source_id is not None:
            if source_id not in self.source_spans:
                self.source_spans[source_id] = []
            self.source_spans[source_id].append((char_start, char_end))

    def calculate_overall_similarity(self):
        """
        Calculate the overall similarity percentage.
        
        Returns:
            dict with:
                - overall_similarity: float (0-100)
                - matched_chars: int
                - total_chars: int
                - matched_words_estimate: int
                - source_breakdown: dict of source_id -> percentage
                - match_type_breakdown: dict of match_type -> count
        """
        if not self.all_spans:
            return {
                'overall_similarity': 0.0,
                'matched_chars': 0,
                'total_chars': self.total_text_length,
                'matched_words_estimate': 0,
                'source_breakdown': {},
                'match_type_breakdown': {},
            }

        # Merge overlapping spans
        merged = self._merge_spans([(s[0], s[1]) for s in self.all_spans])
        matched_chars = sum(end - start for start, end in merged)

        # Calculate overall similarity
        overall = (matched_chars / self.total_text_length) * 100
        overall = min(overall, 100.0)

        # Estimate matched words
        chars_per_word = self.total_text_length / self.total_word_count
        matched_words = int(matched_chars / chars_per_word) if chars_per_word > 0 else 0

        # Source breakdown
        source_breakdown = {}
        for source_id, spans in self.source_spans.items():
            merged_source = self._merge_spans(spans)
            source_chars = sum(end - start for start, end in merged_source)
            source_pct = (source_chars / self.total_text_length) * 100
            source_breakdown[source_id] = min(source_pct, 100.0)

        # Match type breakdown
        type_counts = {}
        for span in self.all_spans:
            mt = span[3]
            type_counts[mt] = type_counts.get(mt, 0) + 1

        return {
            'overall_similarity': round(overall, 2),
            'matched_chars': matched_chars,
            'total_chars': self.total_text_length,
            'matched_words_estimate': matched_words,
            'source_breakdown': source_breakdown,
            'match_type_breakdown': type_counts,
        }

    def _merge_spans(self, spans):
        """Merge overlapping character spans."""
        if not spans:
            return []

        sorted_spans = sorted(spans, key=lambda x: x[0])
        merged = [sorted_spans[0]]

        for start, end in sorted_spans[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                # Overlapping or adjacent - merge
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))

        return merged
