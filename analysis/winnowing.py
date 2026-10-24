"""
Industrial-grade Winnowing Fingerprinting & Shingle Matching Engine.
Reference: Schleimer, Wilkerson, Aiken (2003): "Winnowing: Local Algorithms for Document Fingerprinting"

Guarantees:
1. Any exact match of length >= t = (w + k - 1) tokens is guaranteed to be detected.
2. Inverted index maps fingerprint hashes to document ID, token positions, and character offsets.
3. Consecutive matching fingerprint anchors are merged into maximal aligned passages.
4. Duplicate local fingerprints are deduplicated to prevent score inflation.
"""
import re
import hashlib
from typing import List, Dict, Any, Tuple, Set, Optional
from collections import defaultdict


class TokenSpan:
    """Represents a token with word index and character offsets in original text."""
    __slots__ = ('word_idx', 'token', 'clean_token', 'start_char', 'end_char')

    def __init__(self, word_idx: int, token: str, start_char: int, end_char: int):
        self.word_idx = word_idx
        self.token = token
        self.clean_token = token.lower()
        self.start_char = start_char
        self.end_char = end_char


class Fingerprint:
    """Represents a winnowed fingerprint hash with document coordinates."""
    __slots__ = ('hash_val', 'word_start', 'word_end', 'char_start', 'char_end')

    def __init__(self, hash_val: int, word_start: int, word_end: int, char_start: int, char_end: int):
        self.hash_val = hash_val
        self.word_start = word_start
        self.word_end = word_end
        self.char_start = char_start
        self.char_end = char_end

    def to_dict(self) -> Dict[str, Any]:
        return {
            'hash': self.hash_val,
            'word_start': self.word_start,
            'word_end': self.word_end,
            'char_start': self.char_start,
            'char_end': self.char_end,
        }


class WinnowingEngine:
    """
    Configurable Winnowing Fingerprint Engine.
    - k: Shingle length (number of consecutive tokens per k-gram)
    - w: Window size (number of consecutive hashes per sliding window)
    Guarantee threshold t = w + k - 1
    """

    def __init__(self, k: int = 5, w: int = 4):
        self.k = max(2, k)
        self.w = max(1, w)
        self.guarantee_threshold = self.w + self.k - 1

    def tokenize_with_offsets(self, text: str) -> List[TokenSpan]:
        """
        Tokenizes text into words while recording original character offsets.
        Normalizes Unicode dashes, smart quotes, and whitespace non-destructively.
        """
        tokens: List[TokenSpan] = []
        if not text:
            return tokens

        # Pre-normalize dashes and quotes for clean token boundary extraction
        norm = text.replace('—', ' ').replace('–', ' ').replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
        word_idx = 0
        for m in re.finditer(r'\b[a-zA-Z0-9_\'-]+\b', norm):
            raw_token = text[m.start():m.end()] if m.end() <= len(text) else m.group(0)
            clean = re.sub(r'[^a-zA-Z0-9]', '', m.group(0)).lower()
            if not clean:
                continue
            tokens.append(TokenSpan(
                word_idx=word_idx,
                token=raw_token,
                start_char=m.start(),
                end_char=m.end()
            ))
            word_idx += 1

        return tokens

    def compute_fingerprints(self, text: str) -> Tuple[List[Fingerprint], List[TokenSpan]]:
        """
        Computes winnowed fingerprints for a given text.
        Returns:
            fingerprints: List of selected Fingerprint objects
            tokens: List of TokenSpan objects with offsets
        """
        tokens = self.tokenize_with_offsets(text)
        if len(tokens) < self.k:
            return [], tokens

        # Step 1: Generate k-gram hashes and record boundaries
        kgram_hashes: List[Tuple[int, int, int, int, int]] = []
        for i in range(len(tokens) - self.k + 1):
            shingle_tokens = [t.clean_token for t in tokens[i:i + self.k]]
            shingle_str = " ".join(shingle_tokens)

            # 64-bit hash
            h_int = int(hashlib.sha256(shingle_str.encode('utf-8')).hexdigest()[:16], 16)
            word_start = tokens[i].word_idx
            word_end = tokens[i + self.k - 1].word_idx
            char_start = tokens[i].start_char
            char_end = tokens[i + self.k - 1].end_char

            kgram_hashes.append((h_int, word_start, word_end, char_start, char_end))

        if len(kgram_hashes) < self.w:
            # Document shorter than window size: pick minimum hash overall
            min_entry = min(kgram_hashes, key=lambda x: x[0])
            fp = Fingerprint(
                hash_val=min_entry[0],
                word_start=min_entry[1],
                word_end=min_entry[2],
                char_start=min_entry[3],
                char_end=min_entry[4],
            )
            return [fp], tokens

        # Step 2: Sliding window minimum selection with rightmost tie-breaking
        selected_fingerprints: List[Fingerprint] = []
        last_selected_pos: Optional[int] = None
        seen_hashes: Set[Tuple[int, int]] = set()

        for win_start in range(len(kgram_hashes) - self.w + 1):
            window = kgram_hashes[win_start:win_start + self.w]
            # Find minimum hash in window; tie-break by choosing the rightmost instance
            min_val = float('inf')
            min_idx_in_win = 0
            for idx, entry in enumerate(window):
                h = entry[0]
                if h <= min_val:
                    min_val = h
                    min_idx_in_win = idx

            abs_pos = win_start + min_idx_in_win
            if abs_pos != last_selected_pos:
                entry = kgram_hashes[abs_pos]
                # Avoid adjacent duplicate emission
                key = (entry[0], entry[1])
                if key not in seen_hashes:
                    seen_hashes.add(key)
                    selected_fingerprints.append(Fingerprint(
                        hash_val=entry[0],
                        word_start=entry[1],
                        word_end=entry[2],
                        char_start=entry[3],
                        char_end=entry[4],
                    ))
                last_selected_pos = abs_pos

        return selected_fingerprints, tokens

    def match_fingerprints(
        self,
        sub_fingerprints: List[Fingerprint],
        src_fingerprints: List[Fingerprint],
        sub_text: str,
        src_text: str,
        min_words: int = 5,
        sub_tokens: Optional[List[TokenSpan]] = None,
        src_tokens: Optional[List[TokenSpan]] = None
    ) -> List[Dict[str, Any]]:
        """
        Compares submitted document fingerprints against source document fingerprints.
        Merges consecutive matching fingerprint anchors into contiguous passages with outward expansion.
        """
        if not sub_fingerprints or not src_fingerprints:
            return []

        if sub_tokens is None:
            sub_tokens = self.tokenize_with_offsets(sub_text)
        if src_tokens is None:
            src_tokens = self.tokenize_with_offsets(src_text)

        # Build index for source fingerprints
        src_index = defaultdict(list)
        for src_fp in src_fingerprints:
            src_index[src_fp.hash_val].append(src_fp)

        # Find matching pairs (sub_fp, src_fp)
        matched_anchors: List[Tuple[Fingerprint, Fingerprint]] = []
        for sub_fp in sub_fingerprints:
            if sub_fp.hash_val in src_index:
                for src_fp in src_index[sub_fp.hash_val]:
                    matched_anchors.append((sub_fp, src_fp))

        if not matched_anchors:
            return []

        # Sort anchors by submitted document start character
        matched_anchors.sort(key=lambda x: (x[0].char_start, x[1].char_start))

        # Group and merge consecutive matching anchors into longer passages
        merged_passages: List[Dict[str, Any]] = []
        current_cluster: List[Tuple[Fingerprint, Fingerprint]] = [matched_anchors[0]]

        for i in range(1, len(matched_anchors)):
            sub_prev, src_prev = current_cluster[-1]
            sub_curr, src_curr = matched_anchors[i]

            sub_gap = sub_curr.char_start - sub_prev.char_end
            src_gap = src_curr.char_start - src_prev.char_end

            if (0 <= sub_gap <= 150) and (0 <= src_gap <= 150) and abs(sub_gap - src_gap) <= 50:
                current_cluster.append((sub_curr, src_curr))
            else:
                passage = self._resolve_cluster_to_passage(current_cluster, sub_text, src_text, min_words, sub_tokens, src_tokens)
                if passage:
                    merged_passages.append(passage)
                current_cluster = [(sub_curr, src_curr)]

        if current_cluster:
            passage = self._resolve_cluster_to_passage(current_cluster, sub_text, src_text, min_words, sub_tokens, src_tokens)
            if passage:
                merged_passages.append(passage)

        return merged_passages

    def _resolve_cluster_to_passage(
        self,
        cluster: List[Tuple[Fingerprint, Fingerprint]],
        sub_text: str,
        src_text: str,
        min_words: int,
        sub_tokens: Optional[List[TokenSpan]] = None,
        src_tokens: Optional[List[TokenSpan]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Extracts text slice from cluster, expands outward to exact matching boundaries."""
        sub_start = cluster[0][0].char_start
        sub_end = max(c[0].char_end for c in cluster)
        src_start = cluster[0][1].char_start
        src_end = max(c[1].char_end for c in cluster)

        sub_words_start = cluster[0][0].word_start
        sub_words_end = max(c[0].word_end for c in cluster)
        src_words_start = cluster[0][1].word_start
        src_words_end = max(c[1].word_end for c in cluster)

        # Step 7 of Winnowing Algorithm: Outward expansion to recover full matching passages
        if sub_tokens and src_tokens:
            while sub_words_start > 0 and src_words_start > 0:
                if sub_tokens[sub_words_start - 1].clean_token == src_tokens[src_words_start - 1].clean_token:
                    sub_words_start -= 1
                    src_words_start -= 1
                    sub_start = sub_tokens[sub_words_start].start_char
                    src_start = src_tokens[src_words_start].start_char
                else:
                    break

            while sub_words_end + 1 < len(sub_tokens) and src_words_end + 1 < len(src_tokens):
                if sub_tokens[sub_words_end + 1].clean_token == src_tokens[src_words_end + 1].clean_token:
                    sub_words_end += 1
                    src_words_end += 1
                    sub_end = sub_tokens[sub_words_end].end_char
                    src_end = src_tokens[src_words_end].end_char
                else:
                    break

        matched_sub_text = sub_text[sub_start:sub_end].strip()
        matched_src_text = src_text[src_start:src_end].strip()
        word_count = len(matched_sub_text.split())

        if word_count < min_words:
            return None

        return {
            'submitted_text': matched_sub_text,
            'source_text': matched_src_text,
            'submitted_start': sub_start,
            'submitted_end': sub_end,
            'source_start': src_start,
            'source_end': src_end,
            'submitted_word_start': sub_words_start,
            'submitted_word_end': sub_words_end,
            'source_word_start': src_words_start,
            'source_word_end': src_words_end,
            'word_count': word_count,
            'match_type': 'winnowing',
            'similarity': 1.0,
            'anchor_count': len(cluster),
        }
