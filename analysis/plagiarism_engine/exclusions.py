"""
Exclusion Filters Engine & Academic Citation/Quotation Classifier.
==================================================================
Implements toggleable filters for Bibliography (English & Hindi),
Direct Quotations, and Formatted In-Text Citations.
Classifies matches into the Turnitin 4 Match Groups:
- not_cited_or_quoted
- missing_quotations
- missing_citation
- cited_and_quoted
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
from .ingestion import TokenSpan


@dataclass
class ExcludedRegion:
    """Represents a character span excluded from similarity scoring."""
    start_char: int
    end_char: int
    reason: str  # 'bibliography', 'quotation', 'citation'
    matched_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_char": self.start_char,
            "end_char": self.end_char,
            "reason": self.reason,
            "matched_text": self.matched_text,
        }


class ExclusionFiltersEngine:
    """
    Production-Grade Exclusion Engine supporting English & Devanagari scripts.
    Identifies bibliographic sections, quotes, and citations, marking them
    so that matched tokens in excluded regions are not penalized.
    """

    def __init__(
        self,
        exclude_bibliography: bool = True,
        exclude_quotations: bool = True,
        exclude_citations: bool = True,
        min_match_words: int = 8,
    ):
        self.exclude_bibliography = exclude_bibliography
        self.exclude_quotations = exclude_quotations
        self.exclude_citations = exclude_citations
        self.min_match_words = min_match_words

        # English bibliography header pattern
        self.en_bib_header_pattern = re.compile(
            r'(?:^|\n)\s*(?:#+\s*)?(?:references|works\s+cited|bibliography|reference\s+list|literature\s+cited|cited\s+literature|sources\s+cited)\s*[:\n]',
            re.IGNORECASE
        )

        # Hindi (Devanagari) bibliography header pattern
        # संदर्भ सूची, ग्रंथसूची, हवाले, संदर्भ ग्रंथ, संदर्भित साहित्य, संदर्भ ग्रंथ सूची, संदर्भ
        self.hi_bib_header_pattern = re.compile(
            r'(?:^|\n)\s*(?:#+\s*)?(?:संदर्भ\s*ग्रंथ\s*सूची|संदर्भित\s*साहित्य|संदर्भ\s*सूची|संदर्भ\s*ग्रंथ|ग्रंथसूची|हवाले|संदर्भ)\s*[:\n|।]',
            re.UNICODE
        )

        # In-text Citation patterns (English + Hindi)
        self.citation_patterns = [
            # APA / Harvard style English: (Smith, 2024), (Smith et al., 2024), (Smith & Jones, 2023, p. 45)
            re.compile(r'\([A-Z][a-zA-Z\s.,&]+,?\s*(?:19|20)\d{2}(?:[a-z])?(?:,\s*p{1,2}\.?\s*\d+(?:-\d+)?)?\)'),
            re.compile(r'\([A-Z][a-zA-Z\s]+et\s+al\.,?\s*(?:19|20)\d{2}\)', re.IGNORECASE),
            # IEEE / Vancouver numerical: [1], [1, 2], [1-5], [12, 14, 18]
            re.compile(r'\[\s*\d+(?:\s*[,-]\s*\d+)*\s*\]'),
            # Hindi style citations: (शर्मा, 2021), (वर्मा एवं अन्य, 2020), (गुप्ता, 2019, पृष्ठ 12)
            re.compile(r'\([\u0900-\u097F\s.,&]+,?\s*(?:19|20)\d{2}(?:[a-z])?(?:,\s*पृष्ठ\s*\d+)?\)', re.UNICODE),
            re.compile(r'\([\u0900-\u097F\s]+(?:एवं\s+अन्य|व\s+अन्य|तथा\s+अन्य),?\s*(?:19|20)\d{2}\)', re.UNICODE),
        ]

        # Quotation patterns (ASCII, Unicode smart quotes, guillemets, blockquotes)
        self.quote_patterns = [
            re.compile(r'"([^"\n]{3,})"'),              # ASCII double quotes
            re.compile(r'“([^”\n]{3,})”'),              # Curly double quotes
            re.compile(r'«([^»\n]{3,})»'),              # Guillemets
            re.compile(r'„([^“\n]{3,})“'),              # German / Slavic quotes
            re.compile(r"'([^'\n]{5,})'"),              # ASCII single quotes
            re.compile(r'‘([^’\n]{5,})’'),              # Curly single quotes
            re.compile(r'^\s*>\s+.*$', re.MULTILINE),   # Markdown blockquotes
        ]

    def detect_bibliography_regions(self, text: str) -> List[ExcludedRegion]:
        """
        Detects terminal bibliography / reference section in English or Hindi.
        Excludes everything from the matched heading to the end of document.
        """
        regions: List[ExcludedRegion] = []
        doc_len = len(text)
        if doc_len < 100:
            return regions

        # Scan for English and Hindi headers
        matches = []
        for m in self.en_bib_header_pattern.finditer(text):
            matches.append(m)
        for m in self.hi_bib_header_pattern.finditer(text):
            matches.append(m)

        if not matches:
            return regions

        # Select the heading that appears in the latter half or after reasonable length
        # (avoiding any accidental table of contents entry)
        valid_matches = [m for m in matches if m.start() >= doc_len * 0.25 or m.start() > 800]
        if not valid_matches:
            # If doc is short, take the last occurrence
            valid_matches = [matches[-1]]

        chosen_match = valid_matches[-1]
        start_pos = chosen_match.start()
        # Clean heading newline if matched
        if text[start_pos] == '\n':
            start_pos += 1

        regions.append(ExcludedRegion(
            start_char=start_pos,
            end_char=doc_len,
            reason="bibliography",
            matched_text=text[start_pos:min(start_pos + 120, doc_len)]
        ))
        return regions

    def detect_quotation_regions(self, text: str) -> List[ExcludedRegion]:
        """Detects all text spans enclosed in quotation marks or blockquotes."""
        regions: List[ExcludedRegion] = []
        for pat in self.quote_patterns:
            for m in pat.finditer(text):
                regions.append(ExcludedRegion(
                    start_char=m.start(),
                    end_char=m.end(),
                    reason="quotation",
                    matched_text=m.group(0)
                ))
        return regions

    def detect_citation_regions(self, text: str) -> List[ExcludedRegion]:
        """Detects all in-text citations matching English or Devanagari patterns."""
        regions: List[ExcludedRegion] = []
        for pat in self.citation_patterns:
            for m in pat.finditer(text):
                regions.append(ExcludedRegion(
                    start_char=m.start(),
                    end_char=m.end(),
                    reason="citation",
                    matched_text=m.group(0)
                ))
        return regions

    def get_all_exclusions(self, text: str) -> List[ExcludedRegion]:
        """
        Gathers all active exclusions based on configuration flags and merges overlaps.
        """
        raw_regions: List[ExcludedRegion] = []

        if self.exclude_bibliography:
            raw_regions.extend(self.detect_bibliography_regions(text))

        if self.exclude_quotations:
            raw_regions.extend(self.detect_quotation_regions(text))

        if self.exclude_citations:
            raw_regions.extend(self.detect_citation_regions(text))

        return self._merge_regions(raw_regions)

    def get_excluded_token_indices(
        self,
        tokens: List[TokenSpan],
        exclusions: List[ExcludedRegion]
    ) -> Set[int]:
        """
        Maps character-level excluded regions to discrete token indices in the document.
        """
        excluded_tokens: Set[int] = set()
        if not exclusions or not tokens:
            return excluded_tokens

        # Sort exclusions by start_char
        for ex in exclusions:
            for t in tokens:
                # Overlap between token [start_char, end_char] and exclusion [ex.start_char, ex.end_char]
                if max(t.start_char, ex.start_char) < min(t.end_char, ex.end_char):
                    excluded_tokens.add(t.token_index)

        return excluded_tokens

    def classify_match_span(
        self,
        start_char: int,
        end_char: int,
        full_text: str
    ) -> str:
        """
        Classifies a matched document snippet into one of Turnitin's 4 Match Groups:
        1. "cited_and_quoted": Both quotation marks and in-text citation present.
        2. "missing_quotations": In-text citation present, but quotation marks missing.
        3. "missing_citation": Quotation marks present, but in-text citation missing.
        4. "not_cited_or_quoted": Neither citation nor quotation marks present.
        """
        snippet = full_text[start_char:end_char].strip()
        # Look around snippet boundaries (+- 60 characters) for adjacent citation or quotes
        context_start = max(0, start_char - 60)
        context_end = min(len(full_text), end_char + 60)
        context = full_text[context_start:context_end]

        # Check 1: Quotation marks
        has_quotes = False
        # In snippet itself
        if (snippet.startswith(('"', '“', "'", '‘', '«')) and snippet.endswith(('"', '”', "'", '’', '»'))):
            has_quotes = True
        elif ('"' in snippet or '“' in snippet or '”' in snippet or '«' in snippet or '»' in snippet):
            has_quotes = True
        else:
            # Check if immediately flanked by quotes in context
            before = full_text[max(0, start_char - 3):start_char].strip()
            after = full_text[end_char:min(len(full_text), end_char + 3)].strip()
            if before.endswith(('"', '“', '‘', '«')) and after.startswith(('"', '”', '’', '»')):
                has_quotes = True

        # Check 2: Citation presence in snippet or trailing context
        has_citation = False
        trailing_window = full_text[start_char:context_end]
        for pat in self.citation_patterns:
            if pat.search(trailing_window) or pat.search(context):
                has_citation = True
                break

        # Classify into Turnitin 4 Groups
        if has_quotes and has_citation:
            return "cited_and_quoted"
        elif has_citation and not has_quotes:
            return "missing_quotations"
        elif has_quotes and not has_citation:
            return "missing_citation"
        else:
            return "not_cited_or_quoted"

    @staticmethod
    def _merge_regions(regions: List[ExcludedRegion]) -> List[ExcludedRegion]:
        """Merges overlapping or adjacent excluded regions."""
        if not regions:
            return []
        sorted_regions = sorted(regions, key=lambda r: (r.start_char, r.end_char))
        merged: List[ExcludedRegion] = [sorted_regions[0]]
        for r in sorted_regions[1:]:
            prev = merged[-1]
            if r.start_char <= prev.end_char:
                # Merge overlapping spans, keeping combined reason if different
                prev.end_char = max(prev.end_char, r.end_char)
                if prev.reason != r.reason:
                    prev.reason = f"{prev.reason}+{r.reason}"
            else:
                merged.append(r)
        return merged
