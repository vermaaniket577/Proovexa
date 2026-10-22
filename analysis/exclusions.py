"""
Exclusion logic for similarity analysis.
Handles bibliography, quotations, citations, common phrases, etc.
"""
import re
import logging

logger = logging.getLogger(__name__)


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
        
        Args:
            match_data: dict with match information
            document_text: full document text for context checking
        
        Returns:
            tuple: (should_exclude: bool, reason: str, uncertain: bool)
        """
        submitted_text = match_data.get('submitted_text', '')
        word_count = len(submitted_text.split())

        # Check minimum word count
        min_words = self.settings.get('min_match_words', 5)
        if word_count < min_words:
            return True, f'Below minimum word count ({min_words})', False

        # Check bibliography exclusion
        if self.settings.get('exclude_bibliography', False):
            is_bib, certain = self._is_bibliography(submitted_text, document_text)
            if is_bib:
                if certain:
                    return True, 'Bibliography/reference section', False
                else:
                    return False, 'Possibly in bibliography (marked for review)', True

        # Check quotation exclusion
        if self.settings.get('exclude_quotations', False):
            is_quote, certain = self._is_quotation(submitted_text, document_text)
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

    def _is_bibliography(self, text, full_text):
        """
        Check if text appears to be in a bibliography/reference section.
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

        # Check if text appears after bibliography headers in the full document
        if full_text:
            bib_headers = [
                r'\bReferences\b', r'\bBibliography\b', r'\bWorks\s+Cited\b',
                r'\bReference\s+List\b', r'\bCited\s+Literature\b',
            ]
            for header in bib_headers:
                header_match = re.search(header, full_text, re.IGNORECASE)
                if header_match:
                    bib_start = header_match.start()
                    text_pos = full_text.find(text)
                    if text_pos > bib_start:
                        return True, False  # Uncertain - may have content after refs

        return False, False

    def _is_quotation(self, text, full_text):
        """
        Check if text appears to be a direct quotation.
        Returns (is_quotation, is_certain).
        """
        # Check for quotation marks around the text
        stripped = text.strip()

        # Direct quotes with proper quotation marks
        if (stripped.startswith('"') and stripped.endswith('"')) or \
           (stripped.startswith('\u201c') and stripped.endswith('\u201d')) or \
           (stripped.startswith("'") and stripped.endswith("'")):
            return True, True

        # Check context in full document
        if full_text:
            text_pos = full_text.find(text.strip())
            if text_pos > 0:
                # Check characters before and after
                before = full_text[max(0, text_pos - 5):text_pos].strip()
                after_end = min(len(full_text), text_pos + len(text) + 5)
                after = full_text[text_pos + len(text):after_end].strip()

                if before.endswith('"') or before.endswith('\u201c'):
                    if after.startswith('"') or after.startswith('\u201d'):
                        return True, True
                    return True, False  # Uncertain

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
        if self.settings.get('min_match_words', 5) != 5:
            summary.append(f"Minimum match: {self.settings['min_match_words']} words")
        if self.settings.get('exclude_common_phrases'):
            summary.append('Common phrases excluded')
        if self.settings.get('exclude_self_match'):
            summary.append('Self-matching disabled')
        return summary or ['No exclusions applied']
