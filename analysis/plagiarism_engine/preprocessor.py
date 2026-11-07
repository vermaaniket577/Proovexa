"""
Bilingual Normalization & Tokenization Engine (English + Hindi Devanagari).
===========================================================================
Applies NFKC normalization, Nukta unification, ZWJ/ZWNJ invariant stripping,
Halant-aware conjunct binding, and maintains exact original manuscript token offsets.
"""

from __future__ import annotations
import re
import unicodedata
from typing import List, Dict, Any, Optional, Tuple
from .ingestion import TokenSpan, ParagraphSpan


# Devanagari characters:
# Range \u0900-\u097F includes vowels, consonants, signs, matras, halant, nukta.
# Also include ZWNJ (\u200C) and ZWJ (\u200D) so tokens retain them in original_word/offsets.
# Exclude Danda (\u0964) and Double Danda (\u0965) from word tokens so they act as sentence delimiters.
DEV_WORD_CHARS = r'\u0900-\u0963\u0966-\u097F\u200c\u200d'

# Unified word regex: matches Hindi and English word tokens, preserving hyphens and apostrophes inside words
# Does NOT break words at Halant (\u094D), Matras (\u093E-\u094C), or Nukta (\u093C).
WORD_TOKEN_REGEX = re.compile(
    rf'[{DEV_WORD_CHARS}a-zA-Z0-9]+(?:[-’\'][{DEV_WORD_CHARS}a-zA-Z0-9]+)*'
)

# Canonical Nukta Mapping Table:
# Maps decomposed (base consonant + Nukta \u093c) and precomposed equivalents to canonical form.
DEVANAGARI_NUKTA_MAP = {
    '\u0915\u093c': '\u0958',  # क + ़ -> क़
    '\u0916\u093c': '\u0959',  # ख + ़ -> ख़
    '\u0917\u093c': '\u095a',  # ग + ़ -> ग़
    '\u091c\u093c': '\u095b',  # ज + ़ -> ज़
    '\u0921\u093c': '\u095c',  # ड + ़ -> ड़
    '\u0922\u093c': '\u095d',  # ढ + ़ -> ढ़
    '\u092b\u093c': '\u095e',  # फ + ़ -> फ़
    '\u092f\u093c': '\u095f',  # य + ़ -> य़
}

# Smart quotes and dashes mapping to standard ASCII
PUNCTUATION_SUBSTITUTIONS = {
    '“': '"', '”': '"', '«': '"', '»': '"', '„': '"',
    '‘': "'", '’': "'", '‚': "'", '`': "'",
    '—': ' - ', '–': ' - ',
}


class BilingualPreprocessor:
    """
    Industrial-Grade Bilingual Text Normalizer & Tokenizer for Plagiarism Detection.
    Guarantees exact character offset tracking on original manuscripts while computing
    invariant normalized representations for fingerprinting and shingling.
    """

    def __init__(self):
        # Compiled regex for smart quote normalization
        self.quote_regex = re.compile(r'[“”«»„‘’‚`—–]')
        # Compiled regex for zero-width characters (ZWNJ \u200C, ZWJ \u200D, BOM \uFEFF)
        self.zero_width_regex = re.compile(r'[\u200b\u200c\u200d\u200e\u200f\ufeff]')

    def normalize_text_nfkc(self, text: str) -> str:
        """
        Applies Unicode NFKC normalization and standardizes smart quotes.
        Preserves string length if used non-destructively.
        """
        if not text:
            return ""
        norm = unicodedata.normalize('NFKC', text)
        return norm

    def normalize_hindi_nukta(self, text: str) -> str:
        """
        Normalizes Devanagari Nukta variations into unified canonical precomposed forms:
        - Decomposed sequences (e.g. ज + ़ \u091c\u093c) -> precomposed ज़ (\u095b)
        - Prevents hash divergence when sources mix typing conventions.
        """
        if not text:
            return ""
        # First ensure NFKC so standard compositions take effect
        res = unicodedata.normalize('NFKC', text)
        for decomposed, precomposed in DEVANAGARI_NUKTA_MAP.items():
            res = res.replace(decomposed, precomposed)
        return res

    def strip_zero_width_for_hash(self, text: str) -> str:
        """
        Strips Zero-Width Non-Joiner (ZWNJ \u200C), Zero-Width Joiner (ZWJ \u200D),
        and soft hyphens for invariant fingerprint hashing.
        """
        if not text:
            return ""
        return self.zero_width_regex.sub('', text)

    def normalize_word_token(self, token_str: str) -> str:
        """
        Computes the invariant normalized form of a single token:
        1. NFKC Unicode normalization.
        2. Nukta canonicalization (ज़ vs ज+़).
        3. Stripping ZWJ/ZWNJ/BOM.
        4. Lowercase folding for English and Latin scripts.
        """
        # Step 1: NFKC
        norm = unicodedata.normalize('NFKC', token_str)
        # Step 2: Canonical Nukta
        norm = self.normalize_hindi_nukta(norm)
        # Step 3: Strip ZWJ / ZWNJ
        norm = self.strip_zero_width_for_hash(norm)
        # Step 4: Case-fold
        norm = norm.lower()
        # Clean any remaining non-word edge punctuation (e.g. trailing period/comma in raw slice)
        norm = norm.strip(".,;:?!\"'()[]{}«»`~")
        return norm

    def tokenize_with_offsets(
        self,
        full_text: str,
        paragraphs: Optional[List[ParagraphSpan]] = None
    ) -> List[TokenSpan]:
        """
        Tokenizes text into words while recording EXACT character start and end offsets,
        line numbers, page numbers, and paragraph coordinates on the original text.
        
        Hindi Specifics:
        - Halant (\u094D) conjuncts (e.g., 'दृष्टिकोण', 'प्रणाली') are bound into single words.
        - Matras (\u093E-\u094C) are kept attached to preceding consonants.
        
        English Specifics:
        - Lowercase folding, hyphenated compounds preserved ('state-of-the-art').
        """
        tokens: List[TokenSpan] = []
        if not full_text:
            return tokens

        # Pre-compute paragraph lookups if provided
        para_lookup = []
        if paragraphs:
            for p in paragraphs:
                para_lookup.append((p.start_char, p.end_char, p.paragraph_index, p.page_number, p.line_number))

        # Compute line offsets for fast line number resolution
        line_starts = [0]
        for m in re.finditer(r'\n', full_text):
            line_starts.append(m.end())

        def get_line_number(char_pos: int) -> int:
            import bisect
            return bisect.bisect_right(line_starts, char_pos)

        def get_para_and_page(char_pos: int) -> Tuple[int, int]:
            if not para_lookup:
                return (1, 1)
            for start, end, p_idx, page_idx, _ in para_lookup:
                if start <= char_pos <= end:
                    return (p_idx, page_idx)
            # Default to nearest or last
            return (para_lookup[-1][2], para_lookup[-1][3])

        token_idx = 0
        for match in WORD_TOKEN_REGEX.finditer(full_text):
            start_char = match.start()
            end_char = match.end()
            raw_word = full_text[start_char:end_char]

            normalized = self.normalize_word_token(raw_word)
            if not normalized:
                continue

            line_num = get_line_number(start_char)
            para_num, page_num = get_para_and_page(start_char)

            token_span = TokenSpan(
                token_index=token_idx,
                start_char=start_char,
                end_char=end_char,
                original_word=raw_word,
                normalized_word=normalized,
                line_number=line_num,
                page_number=page_num,
                paragraph_index=para_num
            )
            tokens.append(token_span)
            token_idx += 1

        return tokens

    def detect_language(self, text: str) -> str:
        """
        Bilingual language detector:
        - Returns 'hi-IN' if primarily Hindi/Devanagari script.
        - Returns 'en-IN' if primarily English prose.
        - Returns 'mixed' if document contains both languages significantly.
        """
        if not text or len(text.strip()) < 10:
            return "en-IN"

        sample = text[:15000]
        devanagari_chars = sum(1 for c in sample if '\u0900' <= c <= '\u097F')
        latin_chars = sum(1 for c in sample if ('a' <= c <= 'z') or ('A' <= c <= 'Z'))
        total_letters = devanagari_chars + latin_chars

        if total_letters == 0:
            return "en-IN"

        dev_ratio = devanagari_chars / total_letters
        latin_ratio = latin_chars / total_letters

        if dev_ratio >= 0.70:
            return "hi-IN"
        elif latin_ratio >= 0.70:
            return "en-IN"
        elif dev_ratio >= 0.20 and latin_ratio >= 0.20:
            return "mixed"
        elif dev_ratio >= 0.35:
            return "hi-IN"
        else:
            return "en-IN"
