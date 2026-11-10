"""
Dynamic Top Sources Calculation Engine & Data Transformer.

Implements:
1. Multilingual Tokenization with Unicode NFKC normalization and Devanagari (Hindi) support.
2. Greedy Set-Cover Token Attribution to eliminate overlap across sources.
3. Turnitin-Standard Percentage Formatting Rules:
   - 0% omitted from Top Sources.
   - 0% < P < 1.0% formatted as "<1%".
   - P >= 1.0% rounded to nearest integer (f"{round(P)}%").
4. Turnitin 4-Color Theme Cycling (pink, blue, teal, purple).
5. Exact Structured JSON Output Data Model.
"""
import re
import unicodedata
from typing import List, Dict, Any, Set, Tuple, Optional


# Turnitin Official 4-Color Theme Cycling Specification
TOP_SOURCES_THEMES = [
    {
        'theme_name': 'pink',
        'rank_badge_bg': '#C2185B',
        'pill_bg': '#FCE4EC',
        'pill_text': '#880E4F',
    },
    {
        'theme_name': 'blue',
        'rank_badge_bg': '#1976D2',
        'pill_bg': '#E3F2FD',
        'pill_text': '#0D47A1',
    },
    {
        'theme_name': 'teal',
        'rank_badge_bg': '#00796B',
        'pill_bg': '#E0F2F1',
        'pill_text': '#004D40',
    },
    {
        'theme_name': 'purple',
        'rank_badge_bg': '#6A1B9A',
        'pill_bg': '#F3E5F5',
        'pill_text': '#4A148C',
    },
]


def tokenize_multilingual(text: str) -> List[str]:
    """
    Multilingual word tokenizer supporting English and Indic scripts (Devanagari \u0900-\u097F).
    
    1. Applies Unicode NFKC normalization (composing characters, resolving presentation forms).
    2. Recognizes Devanagari conjuncts, Nuktas, and Matras as cohesive token parts.
    3. Handles hyphenated words, apostrophes, and standard alphanumeric tokens.
    """
    if not text:
        return []
    
    normalized = unicodedata.normalize('NFKC', str(text))
    
    # Pattern matches:
    # 1. Indic/Devanagari character sequences including vowels, consonants, virama, nukta, matras (\u0900-\u0963, \u0966-\u097F - excluding dandas \u0964, \u0965)
    # 2. Standard alphanumeric words with optional internal apostrophe or hyphen
    pattern = re.compile(
        r'[\u0900-\u0963\u0966-\u097F]+(?:[’\'-][\u0900-\u0963\u0966-\u097F]+)*|'
        r'[\w\u00C0-\u024F]+(?:[’\'-][\w\u00C0-\u024F]+)*',
        re.UNICODE
    )
    tokens = pattern.findall(normalized)
    return tokens


def normalize_source_type(source_type_str: str, url: str = '', title: str = '') -> str:
    """
    Normalizes arbitrary source categories to standard Turnitin source type tags:
    - 'Publication'
    - 'Internet'
    - 'Submitted works'
    """
    c = (source_type_str or '').lower().strip()
    t = (title or '').lower().strip()
    u = (url or '').lower().strip()

    if any(k in c for k in ['submitted', 'student', 'uploaded', 'assignment', 'internal', 'thesis', 'dissertation']) or \
       any(k in t for k in ['university', 'üniversitesi', 'institute of technology', 'college']):
        return 'Submitted works'

    if any(k in c for k in ['publication', 'academic', 'journal', 'crossref', 'pubmed', 'arxiv', 'springer', 'ieee', 'elsevier']) or \
       'doi.org' in u or 'arxiv.org' in u or 'nih.gov' in u or 'sciencedirect' in u:
        return 'Publication'

    if any(k in c for k in ['web', 'internet', 'online', 'blog', 'wikipedia', 'crawl']):
        return 'Internet'

    # Check for domain extension in title or URL
    if re.search(r'\.(?:org|edu|ac|com|net|gov|io|ai|dz|ke|za|uk|ph|my|np|th|hk|us|et|lk|gh|nz)\b', t) or \
       re.search(r'https?://[^\s]+', u):
        return 'Internet'

    return 'Publication'


def format_similarity_percentage(attributed_words: int, total_words: int) -> Tuple[Optional[str], float]:
    """
    Turnitin-Standard Percentage Formatting Rules:
    - If P == 0%: returns (None, 0.0) -> omitted from Top Sources.
    - If 0% < P < 1.0%: returns ("<1%", P)
    - If P >= 1.0%: returns (f"{round(P)}%", P)
    """
    if total_words <= 0 or attributed_words <= 0:
        return None, 0.0

    raw_pct = (attributed_words / float(total_words)) * 100.0

    if raw_pct <= 0.0:
        return None, 0.0
    elif raw_pct < 0.999:
        return "<1%", round(raw_pct, 2)
    else:
        return f"{int(round(raw_pct))}%", round(raw_pct, 2)


class CandidateSource:
    """Represents a matched candidate source with token spans."""
    def __init__(
        self,
        source_id: Any,
        source_name: str,
        source_url: str = '',
        source_type: str = 'Publication',
        spans: Optional[List[Tuple[int, int]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.source_id = source_id
        self.source_name = source_name or f"Source {source_id}"
        self.source_url = source_url or ''
        self.source_type = normalize_source_type(source_type, source_url, source_name)
        self.spans: List[Tuple[int, int]] = spans or []
        self.metadata = metadata or {}
        self._token_indices: Optional[Set[int]] = None

    def get_token_indices(self, max_tokens: int) -> Set[int]:
        if self._token_indices is None:
            indices = set()
            for start, end in self.spans:
                clamped_start = max(0, min(start, max_tokens - 1))
                clamped_end = max(0, min(end, max_tokens - 1))
                if clamped_start <= clamped_end:
                    indices.update(range(clamped_start, clamped_end + 1))
            self._token_indices = indices
        return self._token_indices

    @property
    def raw_match_count(self) -> int:
        if self._token_indices is not None:
            return len(self._token_indices)
        # Fast estimation from spans if not cached
        covered = set()
        for start, end in self.spans:
            if start <= end:
                covered.update(range(start, end + 1))
        return len(covered)


def calculate_non_overlapping_top_sources(
    total_tokens: int,
    candidate_sources: List[CandidateSource],
    min_match_threshold: int = 8,
    full_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Greedy Set-Cover Token Attribution:
    1. Document tokens represented as [0, 1, ..., N-1].
    2. Maintains boolean array claimed_tokens = [False] * N.
    3. Sorts candidate sources in descending order by raw match count.
    4. Iteratively attributes unclaimed tokens to the top candidates.
    5. Discards or relegates sources where unclaimed_count < min_match_threshold.
    6. Ensures individual source percentages never sum to more than overall similarity.
    7. Applies 4-color cycling themes and percentage display rules.
    """
    N = max(1, total_tokens)
    claimed_tokens = [False] * N

    # Sort candidate sources in descending order by raw match count
    sorted_candidates = sorted(
        candidate_sources,
        key=lambda s: s.get_token_indices(N) and len(s.get_token_indices(N)),
        reverse=True
    )

    top_sources: List[Dict[str, Any]] = []
    overlapping_sources: List[Dict[str, Any]] = []
    rank = 1

    for candidate in sorted_candidates:
        candidate_tokens = candidate.get_token_indices(N)
        if not candidate_tokens:
            continue

        # Count how many matched tokens are currently unclaimed
        unclaimed_tokens = [idx for idx in candidate_tokens if not claimed_tokens[idx]]
        unclaimed_count = len(unclaimed_tokens)

        # Evaluate against threshold
        if unclaimed_count >= min_match_threshold:
            # Attribute unclaimed tokens to this source
            for idx in unclaimed_tokens:
                claimed_tokens[idx] = True

            sim_display, raw_pct = format_similarity_percentage(unclaimed_count, N)
            if sim_display is None:
                continue

            # Color theme cycling (1 -> pink, 2 -> blue, 3 -> teal, 4 -> purple)
            theme_idx = (rank - 1) % len(TOP_SOURCES_THEMES)
            theme = TOP_SOURCES_THEMES[theme_idx]

            source_item = {
                'rank': rank,
                'index': rank,
                'source_id': str(candidate.source_id),
                'source_type': candidate.source_type,
                'sourceType': candidate.source_type,
                'type': candidate.source_type,
                'category': candidate.source_type,
                'source_name': candidate.source_name,
                'sourceName': candidate.source_name,
                'name': candidate.source_name,
                'title': candidate.source_name,
                'source_url': candidate.source_url,
                'url': candidate.source_url,
                'matched_words': unclaimed_count,
                'words': unclaimed_count,
                'raw_matched_words': len(candidate_tokens),
                'similarity_display': sim_display,
                'percent': sim_display,
                'percent_display': sim_display,
                'pct_display': sim_display,
                'percentage': raw_pct,
                'similarityPercentage': raw_pct,
                'color_theme': theme['theme_name'],
                'color': theme['rank_badge_bg'],
                'color_code': theme['rank_badge_bg'],
                'badge_color': theme['rank_badge_bg'],
                'pill_bg': theme['pill_bg'],
                'pill_text': theme['pill_text'],
                'pastel_bg': theme['pill_bg'],
                'bg_color': theme['pill_bg'],
            }
            # Merge any extra metadata (e.g. doi, publication date)
            if candidate.metadata:
                for k, v in candidate.metadata.items():
                    if k not in source_item:
                        source_item[k] = v

            top_sources.append(source_item)
            rank += 1
        else:
            # Relegate to secondary overlapping source
            overlapping_sources.append({
                'source_id': str(candidate.source_id),
                'source_name': candidate.source_name,
                'source_type': candidate.source_type,
                'raw_matched_words': len(candidate_tokens),
                'unclaimed_words': unclaimed_count,
                'relegation_reason': 'Below threshold' if unclaimed_count > 0 else 'Completely overlapped'
            })

    total_attributed_words = sum(claimed_tokens)
    overall_similarity_pct = round((total_attributed_words / float(N)) * 100.0, 2)
    overall_sim_display = f"{int(round(overall_similarity_pct))}%" if overall_similarity_pct >= 0.999 else ("<1%" if overall_similarity_pct > 0 else "0%")

    return {
        'top_sources_header': {
            'title': 'Top Sources',
            'description': 'The sources with the highest number of matches within the submission. Overlapping sources will not be displayed.'
        },
        'top_sources': top_sources,
        'overlapping_sources': overlapping_sources,
        'total_words': N,
        'total_attributed_words': total_attributed_words,
        'overall_similarity_percentage': overall_similarity_pct,
        'overall_similarity_display': overall_sim_display,
        'source_count': len(top_sources),
    }
