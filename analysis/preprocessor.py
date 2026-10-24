"""
Academic Text Preprocessing & Segmentation Pipeline.
Decouples text normalization, language verification, paragraph structure preservation,
and robust academic sentence tokenization with character offsets.
"""
import re
import unicodedata
from typing import List, Dict, Any, Tuple


# Academic abbreviations that should not trigger sentence boundaries
ACADEMIC_ABBREVIATIONS = {
    'al', 'et', 'eg', 'e.g', 'ie', 'i.e', 'cf', 'viz', 'vs', 'etc',
    'fig', 'figs', 'vol', 'vols', 'no', 'nos', 'pp', 'p', 'ed', 'eds',
    'ref', 'refs', 'eq', 'eqs', 'dr', 'prof', 'mr', 'mrs', 'ms',
    'ph.d', 'phd', 'm.sc', 'msc', 'b.sc', 'bsc', 'b.a', 'm.a',
    'univ', 'dept', 'assn', 'co', 'corp', 'inc', 'ltd', 'usa', 'uk'
}


class PreprocessedSentence:
    """Represents a segmented sentence with document coordinates."""
    __slots__ = ('index', 'text', 'clean_text', 'start_char', 'end_char',
                 'paragraph_index', 'word_count', 'token_count')

    def __init__(self, index: int, text: str, start_char: int, end_char: int,
                 paragraph_index: int):
        self.index = index
        self.text = text
        self.clean_text = re.sub(r'\s+', ' ', text).strip()
        self.start_char = start_char
        self.end_char = end_char
        self.paragraph_index = paragraph_index
        tokens = self.clean_text.split()
        self.word_count = len(tokens)
        self.token_count = len(re.findall(r'\b\w+\b', self.clean_text))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'index': self.index,
            'text': self.text,
            'clean_text': self.clean_text,
            'start_char': self.start_char,
            'end_char': self.end_char,
            'paragraph_index': self.paragraph_index,
            'word_count': self.word_count,
            'token_count': self.token_count,
        }


class PreprocessedParagraph:
    """Represents a segmented paragraph with its sentences."""
    def __init__(self, index: int, text: str, start_char: int, end_char: int):
        self.index = index
        self.text = text
        self.start_char = start_char
        self.end_char = end_char
        self.sentences: List[PreprocessedSentence] = []

    @property
    def word_count(self) -> int:
        return sum(s.word_count for s in self.sentences)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'index': self.index,
            'text': self.text,
            'start_char': self.start_char,
            'end_char': self.end_char,
            'word_count': self.word_count,
            'sentence_count': len(self.sentences),
            'sentences': [s.to_dict() for s in self.sentences],
        }


class DocumentPreprocessor:
    """
    Modular text preprocessor tailored for academic documents.
    Handles text normalization, paragraph parsing, and abbreviation-aware sentence splitting.
    """

    def __init__(self):
        # Compile abbreviation regex
        abbr_pattern = r'\b(?:' + '|'.join(re.escape(a) for a in ACADEMIC_ABBREVIATIONS) + r')\.'
        self.abbr_regex = re.compile(abbr_pattern, re.IGNORECASE)

    def normalize_text(self, text: str) -> str:
        """Normalize Unicode characters, smart quotes, dashes, and extra whitespace."""
        if not text:
            return ""
        # Standardize Unicode (NFC)
        text = unicodedata.normalize('NFC', text)
        # Normalize smart quotes and dashes to standard ASCII
        text = text.replace('“', '"').replace('”', '"')
        text = text.replace('‘', "'").replace('’', "'")
        text = text.replace('—', ' - ').replace('–', ' - ')
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        # Remove null bytes or control characters except tabs/newlines
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        return text

    def detect_language(self, text: str) -> Dict[str, Any]:
        """
        Lightweight, transparent language verification for English academic prose.
        Calculates the density of standard English stop words and character frequencies.
        """
        if not text or len(text.strip()) < 20:
            return {'language': 'unknown', 'is_english': False, 'confidence': 0.0}

        english_stopwords = {
            'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i',
            'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at',
            'this', 'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her',
            'she', 'or', 'an', 'will', 'my', 'one', 'all', 'would', 'there',
            'their', 'what', 'so', 'up', 'out', 'if', 'about', 'who', 'get',
            'which', 'go', 'me', 'when', 'make', 'can', 'like', 'time', 'no',
            'just', 'him', 'know', 'take', 'people', 'into', 'year', 'your',
            'good', 'some', 'could', 'them', 'see', 'other', 'than', 'then',
            'now', 'look', 'only', 'come', 'its', 'over', 'think', 'also'
        }

        words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{2,}\b', text[:5000])]
        if not words:
            return {'language': 'unknown', 'is_english': False, 'confidence': 0.0}

        match_count = sum(1 for w in words if w in english_stopwords)
        ratio = match_count / len(words)

        is_english = ratio >= 0.18
        confidence = min(1.0, round(ratio / 0.35, 2)) if is_english else round(ratio / 0.18, 2)

        return {
            'language': 'en' if is_english else 'other',
            'is_english': is_english,
            'confidence': confidence,
            'stopword_ratio': round(ratio, 4),
        }

    def process(self, raw_text: str) -> Tuple[List[PreprocessedParagraph], List[PreprocessedSentence], Dict[str, Any]]:
        """
        Executes complete ingestion pipeline:
        Normalization -> Language check -> Paragraphs -> Sentences with offsets.
        """
        norm_text = self.normalize_text(raw_text)
        lang_info = self.detect_language(norm_text)

        paragraphs: List[PreprocessedParagraph] = []
        all_sentences: List[PreprocessedSentence] = []

        if not norm_text.strip():
            return paragraphs, all_sentences, lang_info

        # Split into paragraphs by double newlines or indentations
        raw_paras = re.split(r'\n\s*\n', norm_text)
        char_cursor = 0
        global_sentence_idx = 1

        for p_idx, p_text in enumerate(raw_paras, 1):
            p_clean = p_text.strip()
            if not p_clean:
                char_cursor += len(p_text) + 2
                continue

            p_start = norm_text.find(p_text, char_cursor)
            if p_start == -1:
                p_start = char_cursor
            p_end = p_start + len(p_text)
            char_cursor = p_end

            para_obj = PreprocessedParagraph(
                index=p_idx,
                text=p_clean,
                start_char=p_start,
                end_char=p_end
            )

            # Segment paragraph into sentences
            sent_spans = self._split_paragraph_sentences(p_clean)
            for s_text, s_rel_start, s_rel_end in sent_spans:
                s_abs_start = p_start + s_rel_start
                s_abs_end = p_start + s_rel_end

                sent_obj = PreprocessedSentence(
                    index=global_sentence_idx,
                    text=s_text,
                    start_char=s_abs_start,
                    end_char=s_abs_end,
                    paragraph_index=p_idx
                )
                para_obj.sentences.append(sent_obj)
                all_sentences.append(sent_obj)
                global_sentence_idx += 1

            paragraphs.append(para_obj)

        stats = {
            'total_characters': len(norm_text),
            'total_words': sum(s.word_count for s in all_sentences),
            'total_paragraphs': len(paragraphs),
            'total_sentences': len(all_sentences),
            'language': lang_info,
        }

        return paragraphs, all_sentences, stats

    def _split_paragraph_sentences(self, text: str) -> List[Tuple[str, int, int]]:
        """
        Splits paragraph text into sentences while respecting academic abbreviations,
        citations (e.g. '[1, 2]', '(Smith et al., 2020)'), and quotation marks.
        Returns list of (sentence_text, rel_start, rel_end).
        """
        # Protect periods in common abbreviations by temporary mask
        masked = text

        def mask_abbr(m):
            return m.group(0).replace('.', '§§DOT§§')

        masked = self.abbr_regex.sub(mask_abbr, masked)
        # Protect numbers like 3.14, 1.2
        masked = re.sub(r'(?<=\d)\.(?=\d)', '§§DOT§§', masked)

        # Sentence end pattern: (. or ? or !) followed by whitespace and an uppercase letter or quote
        pattern = r'([.?!]+["\']?)(?=\s+[A-Z0-9"\'\(\[])'
        parts = re.split(pattern, masked)

        spans: List[Tuple[str, int, int]] = []
        current_offset = 0

        # Combine text parts with their matched punctuation
        i = 0
        while i < len(parts):
            chunk = parts[i]
            punct = parts[i + 1] if (i + 1 < len(parts)) else ""
            i += 2

            raw_sentence = (chunk + punct).replace('§§DOT§§', '.')
            s_clean = raw_sentence.strip()
            if not s_clean:
                continue

            rel_start = text.find(s_clean, current_offset)
            if rel_start == -1:
                rel_start = current_offset
            rel_end = rel_start + len(s_clean)
            current_offset = rel_end

            spans.append((s_clean, rel_start, rel_end))

        if not spans and text.strip():
            spans.append((text.strip(), 0, len(text.strip())))

        return spans
