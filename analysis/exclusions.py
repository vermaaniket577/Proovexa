"""
Exclusion logic for similarity analysis.
Handles bibliography, quotations, citations, common phrases, etc.
"""
import re
import logging

logger = logging.getLogger(__name__)


def filter_bibliography(text: str) -> str:
    """
    Filter bibliography / references from document text.
    Requires section header to be standalone on its own line and appear in the latter
    half of the document (preventing premature truncation on abstract/introductory mentions).
    """
    if not text:
        return text
    pattern = r'(?im)^\s*(references|bibliography|works\s+cited|reference\s+list|cited\s+literature|संदर्भ\s*सूची|ग्रंथसूची)\s*[:.]?\s*$'
    split_parts = re.split(pattern, text)

    # If header found, ensure it is in the latter portion of the document
    if len(split_parts) > 1:
        prefix = split_parts[0]
        # Only truncate if the bibliography appears towards the end (> 50% or after 2500 chars)
        if len(prefix) >= len(text) * 0.50 or (len(text) > 3000 and len(prefix) >= 2500):
            return prefix
    return text


def filter_quotes(text: str) -> str:
    """
    Filter quoted text from document text.
    Only treats as quote if enclosed by matching quotation marks and under 250 words / 1500 chars.
    Prevents an unclosed quote at document start from clearing the entire body.
    """
    if not text:
        return text
    return re.sub(r'["“«][^"”»\n]{5,1500}["”»]', ' ', text)


class ExclusionEngine:
    """Apply exclusion rules to matched passages."""

    def __init__(self, exclusion_settings=None):
        """
        Initialize with exclusion settings.
        
        Args:
            exclusion_settings: dict with keys:
                - exclude_bibliography: bool
                - exclude_quotations: bool
                - exclude_citations: bool
                - min_match_words: int
                - exclude_common_phrases: bool
                - common_phrases_list: list of strings
                - exclude_sources: list of source IDs
                - exclude_self_match: bool
        """
        self.settings = exclusion_settings or {}

    def should_exclude(self, match_data, document_text=''):
        """
        Check if a match should be excluded based on configured rules.
        """
        submitted_text = match_data.get('submitted_text', '')
        word_count = len(submitted_text.split())

        # Check minimum word count
        min_words = self.settings.get('min_match_words', 8)
        if word_count < min_words:
            return True, f'Below minimum word count ({min_words})', False

        # Check bibliography exclusion
        if self.settings.get('exclude_bibliography', False):
            is_bib, certain = self._is_bibliography(submitted_text, document_text, match_data)
            if is_bib:
                if certain:
                    return True, 'Bibliography/reference section', False
                else:
                    return False, 'Possibly in bibliography (marked for review)', True

        # Check quotation exclusion
        if self.settings.get('exclude_quotations', False):
            is_quote, certain = self._is_quotation(submitted_text, document_text, match_data)
            if is_quote:
                if certain:
                    return True, 'Direct quotation', False
                else:
                    return False, 'Possibly a quotation (marked for review)', True

        # Check citation exclusion
        if self.settings.get('exclude_citations', False):
            is_citation, certain = self._is_citation(submitted_text)
            if is_citation:
                if certain:
                    return True, 'Formatted citation', False
                else:
                    return False, 'Possibly a citation (marked for review)', True

        # Check common phrases
        if self.settings.get('exclude_common_phrases', False):
            phrases = self.settings.get('common_phrases_list', [])
            if self._is_common_phrase(submitted_text, phrases):
                return True, 'Common phrase', False

        # Check excluded sources
        excluded_sources = self.settings.get('exclude_sources', [])
        source_id = match_data.get('source_id')
        if source_id and str(source_id) in [str(s) for s in excluded_sources]:
            return True, 'Excluded source', False

        return False, '', False

    def _is_bibliography(self, text, full_text, match_data=None):
        """
        Check if text appears to be in a bibliography/reference section.
        Requires section headers to be standalone on their own line and situated
        in the latter portion of the document.
        Returns (is_bibliography, is_certain).
        """
        # Check if the text itself looks like a reference entry
        bib_patterns = [
            r'^\s*\[\d+\]',  # [1] Author, Title...
            r'^\s*\d+\.\s+\w+,\s+\w+\.?\s*\(',  # 1. Author, F. (year)
            r'^\s*\w+,\s+\w+\.?\s*\(\d{4}\)',  # Author, F. (2024)
            r'doi:\s*\d+\.\d+',  # DOI references
            r'https?://dx\.doi\.org/',
            r'ISBN\s*[\d-]+',
        ]

        for pattern in bib_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True, True

        # Check if text appears after standalone bibliography headers in the full document
        if full_text:
            if getattr(self, '_cached_doc_id', None) != id(full_text):
                self._cached_doc_id = id(full_text)
                self._cached_bib_start = None
                # Standalone header anchor check (supports English and Hindi)
                header_pattern = re.compile(
                    r'(?im)^\s*(?:references|bibliography|works\s+cited|reference\s+list|cited\s+literature|संदर्भ\s*सूची|ग्रंथसूची)\s*[:.]?\s*$'
                )
                matches = list(header_pattern.finditer(full_text))
                doc_len = len(full_text)
                # Only treat as bibliography if header appears in the latter half of the document
                for hm in matches:
                    if hm.start() >= doc_len * 0.50 or (doc_len > 3000 and hm.start() >= 2500):
                        self._cached_bib_start = hm.start()
                        break

            bib_start = getattr(self, '_cached_bib_start', None)
            if bib_start is not None:
                text_pos = match_data.get('submitted_start') if match_data else None
                if text_pos is None:
                    text_pos = full_text.find(text)
                if text_pos is not None and text_pos >= bib_start:
                    return True, True

        return False, False

    def _is_quotation(self, text, full_text, match_data=None):
        """
        Check if text appears to be a direct quotation.
        Guarantees that quotes must be paired and under 250 words / 1500 chars.
        Prevents an unclosed quote from flagging following paragraphs.
        Returns (is_quotation, is_certain).
        """
        stripped = text.strip()
        # Direct quotes must be enclosed by matching quotation marks and bounded
        paired_quotes = [
            ('"', '"'),
            ('“', '”'),
            ('«', '»'),
            ("'", "'"),
        ]
        for q_open, q_close in paired_quotes:
            if stripped.startswith(q_open) and stripped.endswith(q_close) and len(stripped) > 2:
                # Bound maximum quote block: only treat as quote if under 250 words / 1500 chars (prevents runaway quotes)
                if len(stripped.split()) <= 250 and len(stripped) <= 1500:
                    return True, True

        if full_text:
            text_pos = match_data.get('submitted_start') if match_data else None
            if text_pos is None:
                text_pos = full_text.find(stripped)
            if text_pos is not None and text_pos >= 0:
                # Scan full_text for strictly enclosed quote blocks bounded by max length
                if getattr(self, '_cached_quotes_doc_id', None) != id(full_text):
                    self._cached_quotes_doc_id = id(full_text)
                    self._cached_quote_spans = []
                    # Only treat as quote if enclosed and under 1500 chars (prevents runaway quotes)
                    for qm in re.finditer(r'["“«][^"”»\n]{5,1500}["”»]', full_text):
                        self._cached_quote_spans.append((qm.start(), qm.end()))

                text_end = text_pos + len(text)
                for q_start, q_end in getattr(self, '_cached_quote_spans', []):
                    if q_start <= text_pos and text_end <= q_end:
                        return True, True

        return False, False

    def _is_citation(self, text):
        """
        Check if text appears to be a formatted citation.
        Returns (is_citation, is_certain).
        """
        citation_patterns = [
            r'\([\w\s,]+,\s*\d{4}(,\s*p\.\s*\d+)?\)',  # (Author, 2024, p. 5)
            r'\([\w\s&,]+\d{4}\)',  # (Author & Author 2024)
            r'\[[\d,\s-]+\]',  # [1, 2, 3]
            r'\[\d+\]',  # [1]
        ]

        for pattern in citation_patterns:
            if re.match(pattern, text.strip()):
                return True, True

        # Partial citation patterns
        if re.search(r'\(\w+\s+et\s+al\.,?\s*\d{4}\)', text):
            return True, True

        return False, False

    def _is_common_phrase(self, text, phrase_list):
        """Check if text is a common phrase from the list."""
        normalized = text.lower().strip()
        for phrase in phrase_list:
            if phrase.lower().strip() == normalized:
                return True
            if normalized.startswith(phrase.lower().strip()):
                return True
        return False

    def get_settings_summary(self):
        """Return a human-readable summary of exclusion settings."""
        summary = []
        if self.settings.get('exclude_bibliography'):
            summary.append('Bibliography/references excluded')
        if self.settings.get('exclude_quotations'):
            summary.append('Direct quotations excluded')
        if self.settings.get('exclude_citations'):
            summary.append('Formatted citations excluded')
        if self.settings.get('min_match_words', 8) != 8:
            summary.append(f"Minimum match: {self.settings['min_match_words']} words")
        if self.settings.get('exclude_common_phrases'):
            summary.append('Common phrases excluded')
        if self.settings.get('exclude_self_match'):
            summary.append('Self-matching disabled')
        return summary or ['No exclusions applied']
