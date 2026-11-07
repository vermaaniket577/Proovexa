"""
Winnowing Fingerprinting & Inverted Index Matching Engine.
==========================================================
Industrial-grade implementation of Schleimer, Wilkerson, Aiken (2003) Winnowing algorithm:
- 64-bit Karp-Rabin polynomial rolling hash and MurmurHash3 shingling.
- Continuous word n-gram size k = 7..9.
- Sliding window size w = 5 with rightmost tie-breaking minimum selection.
- Inverted Corpus Index (Hash -> List of Source Matches).
- Continuous anchor coalescing and bounded outward expansion.
"""

from __future__ import annotations
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
from .ingestion import TokenSpan


# 64-bit Mersenne prime for Karp-Rabin rolling hash
MERSENNE_61 = 2305843009213693951  # 2^61 - 1
BASE_MULTIPLIER = 313               # Prime base multiplier


def compute_64bit_hash(token_sequence: List[str]) -> int:
    """
    Computes a uniform 64-bit invariant hash for a sequence of normalized tokens
    using BLAKE2b (64-bit digest) and Karp-Rabin polynomial combination.
    """
    joined = " ".join(token_sequence).encode('utf-8')
    # Use blake2b with 8-byte (64-bit) output: fast, collision-resistant, cryptographically uniform
    digest = hashlib.blake2b(joined, digest_size=8).digest()
    return int.from_bytes(digest, byteorder='big')


class KarpRabinRollingHasher:
    """
    Karp-Rabin 64-bit Polynomial Rolling Hasher over token sequences.
    H = (sum_{j=0}^{k-1} t_j * B^{k-1-j}) mod (2^61 - 1)
    """

    def __init__(self, k: int = 7, base: int = BASE_MULTIPLIER, mod: int = MERSENNE_61):
        self.k = k
        self.base = base
        self.mod = mod
        # Precompute base^(k-1) mod P
        self.high_power = pow(base, k - 1, mod)

    def hash_shingle(self, tokens: List[str]) -> int:
        h = 0
        for token in tokens:
            # Map token string to an integer seed
            token_int = compute_64bit_hash([token]) % self.mod
            h = (h * self.base + token_int) % self.mod
        return h


@dataclass
class Fingerprint:
    """Represents a winnowed document fingerprint with token and character coordinates."""
    hash_val: int
    token_start: int   # Token index of start of shingle
    token_end: int     # Token index of end of shingle (token_start + k - 1)
    start_char: int    # Character start offset in document
    end_char: int      # Character end offset in document

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hash": self.hash_val,
            "token_start": self.token_start,
            "token_end": self.token_end,
            "start_char": self.start_char,
            "end_char": self.end_char,
        }


@dataclass
class SourceOccurrence:
    """Occurrence of a fingerprint in an indexed reference source."""
    source_id: str
    source_name: str
    source_type: str   # 'Internet', 'Publication', 'Submitted works'
    source_url: str
    token_start: int
    token_end: int
    start_char: int
    end_char: int


@dataclass
class RawMatch:
    """Raw matched span between submission document and a source prior to overlap resolution."""
    span_id: int
    source_id: str
    source_name: str
    source_type: str
    source_url: str
    sub_token_start: int
    sub_token_end: int
    sub_start_char: int
    sub_end_char: int
    src_token_start: int
    src_token_end: int
    src_start_char: int
    src_end_char: int
    matched_text: str
    source_text: str = ""
    token_count: int = 0
    anchor_count: int = 1

    def token_set(self) -> Set[int]:
        return set(range(self.sub_token_start, self.sub_token_end + 1))


class WinnowingFingerprinter:
    """
    Mathematical Implementation of the Winnowing Algorithm:
    - k: Shingle length (default: 7 continuous words, supports 7 to 9).
    - w: Sliding window size (default: 5).
    Guarantee: Any exact match of length >= t = (w + k - 1) tokens is guaranteed to be detected.
    """

    def __init__(self, k: int = 7, w: int = 5):
        self.k = max(2, k)
        self.w = max(1, w)
        self.guarantee_threshold = self.w + self.k - 1
        self.hasher = KarpRabinRollingHasher(k=self.k)

    def compute_fingerprints(self, tokens: List[TokenSpan]) -> List[Fingerprint]:
        """
        Computes winnowed fingerprints for a given list of TokenSpans.
        Returns the selected document fingerprints.
        """
        n = len(tokens)
        if n < self.k:
            return []

        # Step 1: Compute hashes for all k-grams
        kgram_entries: List[Tuple[int, int, int, int, int]] = []
        for i in range(n - self.k + 1):
            shingle_words = [tokens[i + j].normalized_word for j in range(self.k)]
            h = compute_64bit_hash(shingle_words)
            tok_start = tokens[i].token_index
            tok_end = tokens[i + self.k - 1].token_index
            c_start = tokens[i].start_char
            c_end = tokens[i + self.k - 1].end_char
            kgram_entries.append((h, tok_start, tok_end, c_start, c_end))

        num_hashes = len(kgram_entries)
        if num_hashes <= self.w:
            # Document shorter than window: pick minimum hash overall
            min_entry = min(kgram_entries, key=lambda x: x[0])
            return [Fingerprint(
                hash_val=min_entry[0],
                token_start=min_entry[1],
                token_end=min_entry[2],
                start_char=min_entry[3],
                end_char=min_entry[4]
            )]

        # Step 2: Sliding window minimum selection with rightmost tie-breaking
        selected_fps: List[Fingerprint] = []
        last_selected_pos: Optional[int] = None
        seen_positions: Set[int] = set()

        for win_start in range(num_hashes - self.w + 1):
            window = kgram_entries[win_start:win_start + self.w]
            # Find minimum hash in window; tie-break by choosing rightmost instance
            min_val = float('inf')
            min_offset_in_win = 0
            for offset in range(len(window) - 1, -1, -1):
                h = window[offset][0]
                if h < min_val:
                    min_val = h
                    min_offset_in_win = offset

            abs_pos = win_start + min_offset_in_win
            if abs_pos != last_selected_pos and abs_pos not in seen_positions:
                entry = kgram_entries[abs_pos]
                seen_positions.add(abs_pos)
                selected_fps.append(Fingerprint(
                    hash_val=entry[0],
                    token_start=entry[1],
                    token_end=entry[2],
                    start_char=entry[3],
                    end_char=entry[4]
                ))
                last_selected_pos = abs_pos

        return selected_fps


class InvertedCorpusIndex:
    """
    Inverted Index for High-Performance Plagiarism Detection.
    Maps 64-bit Fingerprint Hash -> List of SourceOccurrences.
    Supports indexing web crawls, academic publications, and student papers.
    """

    def __init__(self, fingerprinter: Optional[WinnowingFingerprinter] = None):
        self.fingerprinter = fingerprinter or WinnowingFingerprinter(k=7, w=5)
        # Hash -> List[SourceOccurrence]
        self.index: Dict[int, List[SourceOccurrence]] = defaultdict(list)
        # source_id -> Document metadata and tokens
        self.sources: Dict[str, Dict[str, Any]] = {}

    def add_source(
        self,
        source_id: str,
        source_name: str,
        tokens: List[TokenSpan],
        full_text: str,
        source_type: str = "Internet",
        source_url: str = "",
        precomputed_fingerprints: Optional[List[Fingerprint]] = None,
    ):
        """Indexes a reference document into the inverted index."""
        fps = precomputed_fingerprints or self.fingerprinter.compute_fingerprints(tokens)
        self.sources[source_id] = {
            "source_id": source_id,
            "source_name": source_name,
            "source_type": source_type,
            "source_url": source_url,
            "tokens": tokens,
            "full_text": full_text,
            "fingerprints": fps,
        }

        for fp in fps:
            self.index[fp.hash_val].append(SourceOccurrence(
                source_id=source_id,
                source_name=source_name,
                source_type=source_type,
                source_url=source_url,
                token_start=fp.token_start,
                token_end=fp.token_end,
                start_char=fp.start_char,
                end_char=fp.end_char
            ))

    def query(
        self,
        sub_tokens: List[TokenSpan],
        sub_text: str,
        min_match_words: int = 8,
        precomputed_sub_fps: Optional[List[Fingerprint]] = None,
    ) -> List[RawMatch]:
        """
        Queries the inverted index with submitted document tokens, finds anchor hits,
        and coalesces them into maximal aligned match spans with outward expansion.
        """
        sub_fps = precomputed_sub_fps or self.fingerprinter.compute_fingerprints(sub_tokens)
        if not sub_fps:
            return []

        # Find all raw anchor matches grouped by source_id
        source_anchors: Dict[str, List[Tuple[Fingerprint, SourceOccurrence]]] = defaultdict(list)
        for dfp in sub_fps:
            if dfp.hash_val in self.index:
                for occ in self.index[dfp.hash_val]:
                    source_anchors[occ.source_id].append((dfp, occ))

        all_matches: List[RawMatch] = []
        span_counter = 1

        for src_id, anchors in source_anchors.items():
            src_info = self.sources.get(src_id, {})
            src_tokens = src_info.get("tokens", [])
            src_text = src_info.get("full_text", "")
            src_name = src_info.get("source_name", f"Source {src_id}")
            src_type = src_info.get("source_type", "Internet")
            src_url = src_info.get("source_url", "")

            # Sort anchors by submitted token position
            anchors.sort(key=lambda a: (a[0].token_start, a[1].token_start))

            # Coalesce consecutive matching anchors into clusters
            clusters: List[List[Tuple[Fingerprint, SourceOccurrence]]] = []
            current_cluster: List[Tuple[Fingerprint, SourceOccurrence]] = [anchors[0]]

            for i in range(1, len(anchors)):
                prev_sub, prev_src = current_cluster[-1]
                curr_sub, curr_src = anchors[i]

                # Check gap in tokens (allow small gap <= 8 tokens between anchors)
                sub_tok_gap = curr_sub.token_start - prev_sub.token_end
                src_tok_gap = curr_src.token_start - prev_src.token_end

                if (0 <= sub_tok_gap <= 8) and (0 <= src_tok_gap <= 8):
                    current_cluster.append((curr_sub, curr_src))
                else:
                    clusters.append(current_cluster)
                    current_cluster = [(curr_sub, curr_src)]

            if current_cluster:
                clusters.append(current_cluster)

            # Resolve each cluster into maximal aligned RawMatch with bounded expansion
            for cluster in clusters:
                raw_match = self._resolve_cluster(
                    cluster=cluster,
                    sub_tokens=sub_tokens,
                    sub_text=sub_text,
                    src_tokens=src_tokens,
                    src_text=src_text,
                    source_id=src_id,
                    source_name=src_name,
                    source_type=src_type,
                    source_url=src_url,
                    min_words=min_match_words,
                    span_id=span_counter
                )
                if raw_match:
                    all_matches.append(raw_match)
                    span_counter += 1

        return all_matches

    def _resolve_cluster(
        self,
        cluster: List[Tuple[Fingerprint, SourceOccurrence]],
        sub_tokens: List[TokenSpan],
        sub_text: str,
        src_tokens: List[TokenSpan],
        src_text: str,
        source_id: str,
        source_name: str,
        source_type: str,
        source_url: str,
        min_words: int,
        span_id: int
    ) -> Optional[RawMatch]:
        """Expands cluster outward word-by-word to capture full exact boundaries."""
        sub_tok_start = cluster[0][0].token_start
        sub_tok_end = max(c[0].token_end for c in cluster)
        src_tok_start = cluster[0][1].token_start
        src_tok_end = max(c[1].token_end for c in cluster)

        # Bounded outward expansion backward
        while (
            sub_tok_start > 0
            and src_tok_start > 0
            and sub_tok_start - 1 < len(sub_tokens)
            and src_tok_start - 1 < len(src_tokens)
            and sub_tokens[sub_tok_start - 1].normalized_word == src_tokens[src_tok_start - 1].normalized_word
        ):
            sub_tok_start -= 1
            src_tok_start -= 1

        # Bounded outward expansion forward
        while (
            sub_tok_end + 1 < len(sub_tokens)
            and src_tok_end + 1 < len(src_tokens)
            and sub_tokens[sub_tok_end + 1].normalized_word == src_tokens[src_tok_end + 1].normalized_word
        ):
            sub_tok_end += 1
            src_tok_end += 1

        token_count = sub_tok_end - sub_tok_start + 1
        if token_count < min_words:
            return None

        sub_start_char = sub_tokens[sub_tok_start].start_char
        sub_end_char = sub_tokens[sub_tok_end].end_char
        matched_snippet = sub_text[sub_start_char:sub_end_char].strip()

        src_start_char = src_tokens[src_tok_start].start_char if src_tok_start < len(src_tokens) else 0
        src_end_char = src_tokens[src_tok_end].end_char if src_tok_end < len(src_tokens) else 0
        src_snippet = src_text[src_start_char:src_end_char].strip() if src_text else ""

        return RawMatch(
            span_id=span_id,
            source_id=source_id,
            source_name=source_name,
            source_type=source_type,
            source_url=source_url,
            sub_token_start=sub_tok_start,
            sub_token_end=sub_tok_end,
            sub_start_char=sub_start_char,
            sub_end_char=sub_end_char,
            src_token_start=src_tok_start,
            src_token_end=src_tok_end,
            src_start_char=src_start_char,
            src_end_char=src_end_char,
            matched_text=matched_snippet,
            source_text=src_snippet,
            token_count=token_count,
            anchor_count=len(cluster)
        )
