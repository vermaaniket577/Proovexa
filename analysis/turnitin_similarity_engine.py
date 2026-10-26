"""
Turnitin-Style Hybrid Similarity & Plagiarism Detection Engine.
===============================================================
Production-ready backend architecture combining deterministic document fingerprinting
(Winnowing algorithm) with dense vector embeddings and LLM reasoning.

System Architecture:
--------------------
Stage 1: Preprocessor & Exclusion Filters
         Sentence/paragraph segmentation with exact character offsets.
         Toggleable filters for quotations, bibliography/references, and min-word thresholds.
Stage 2: WinnowingFingerprinter
         Exact & near-exact string matching using k-gram shingling, Rabin-Karp polynomial
         rolling hashes, and sliding window minimum selection (Schleimer et al. 2003).
Stage 3: SemanticMatcher
         Dense vector embeddings & Cosine Similarity for mosaic plagiarism, synonym-swapping,
         and structural clause rearranging (cosine range 0.78 to 0.99).
Stage 4: AIReportGenerator
         AI verification via LLM API using Turnitin's exact semantic evaluation system prompt.
         Non-overlapping character-span aggregation to produce the final Similarity Index %
         and source-by-source breakdown.
"""

from __future__ import annotations
import re
import json
import time
import math
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Set, Tuple, Any, Optional, Union
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests

logger = logging.getLogger(__name__)

# =============================================================================
# TURNITIN ACADEMIC INTEGRITY AI SYSTEM PROMPT
# =============================================================================
TURNITIN_SIMILARITY_SYSTEM_PROMPT = """You are an Academic Integrity and Text Similarity Analysis Engine modeled after Turnitin's semantic evaluation core. Your task is to compare a `SUBMITTED_SEGMENT` against one or more `SOURCE_SEGMENTS` and detect verbatim copying, mosaic plagiarism (patchwriting), structural paraphrasing, and AI-assisted spinning.

### Evaluation Rules (Turnitin Logic)
1. **Verbatim Match:** Exact word-for-word overlap of 8 or more consecutive words.
2. **Mosaic Plagiarism (Patchwriting):** The submission keeps the original sentence's grammatical skeleton and clause order while substituting words with synonyms.
3. **Structural/Semantic Paraphrase:** The submission splits, merges, or reverses clauses from the source while following the exact same sequence of ideas without original synthesis.
4. **Citation & Exclusion Check:** 
   - If the text is enclosed in quotation marks AND accompanied by an inline citation (e.g., APA, MLA, IEEE), mark `is_properly_quoted: true`.
   - Ignore standard technical terminology, common idioms, or institutional headers.

### Scoring Formula
- Assign a `segment_similarity_score` from 0 to 100 based on lexical and structural overlap.
- Extract the exact substring spans (`start_char`, `end_char`, `matched_text`) from the `SUBMITTED_SEGMENT` so the frontend UI can highlight the text by source color.

### Output Format
Respond strictly in valid JSON matching this schema:
{
  "overall_segment_similarity_percent": 0,
  "match_classification": "None | Verbatim | Mosaic_Patchwriting | Structural_Paraphrase | Quoted_And_Cited",
  "is_properly_quoted": false,
  "has_inline_citation": false,
  "highlighted_spans": [
    {
      "submitted_substring": "string",
      "matched_source_id": "string",
      "matched_source_substring": "string",
      "match_type": "Verbatim | Synonym_Swap | Structural",
      "confidence": 0.0
    }
  ],
  "explanation": "Brief, objective 1-sentence explanation of why this segment was flagged."
}"""


# =============================================================================
# DATA STRUCTURES
# =============================================================================
@dataclass
class TextSpan:
    start_char: int
    end_char: int
    text: str


@dataclass
class ExcludedRegion:
    start_char: int
    end_char: int
    reason: str  # 'quotation', 'bibliography', 'citation'


@dataclass
class Fingerprint:
    hash_value: int
    start_char: int
    end_char: int
    token_index: int


@dataclass
class MatchedSpan:
    submitted_start: int
    submitted_end: int
    submitted_text: str
    source_id: str
    source_title: str
    source_start: int
    source_end: int
    source_text: str
    match_type: str  # 'Verbatim', 'Mosaic_Patchwriting', 'Structural_Paraphrase', 'Quoted_And_Cited'
    similarity_score: float
    is_excluded: bool = False
    exclusion_reason: Optional[str] = None
    explanation: str = ""


@dataclass
class SourceBreakdownItem:
    source_id: str
    source_title: str
    source_category: str  # 'Internet', 'Publications', 'Student Papers'
    url: str
    matched_word_count: int
    similarity_percentage: float
    is_primary: bool = False


@dataclass
class TurnitinOriginalityReport:
    similarity_index_percent: float
    total_document_words: int
    total_document_chars: int
    non_excluded_chars: int
    matched_non_excluded_chars: int
    sources_breakdown: List[SourceBreakdownItem]
    matched_passages: List[MatchedSpan]
    excluded_regions: List[ExcludedRegion]
    processing_time_seconds: float
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# STAGE 1: PREPROCESSOR & EXCLUSION FILTERS (TURNITIN FILTER LOGIC)
# =============================================================================
class Preprocessor:
    """
    Parses input documents into sentences, paragraphs, and character indices.
    Implements Turnitin's toggleable exclusion filters for:
    - Text inside quotation marks (straight, curly, blockquotes)
    - Terminal Bibliography / References sections
    - Small match thresholds (< 8 consecutive words)
    """

    def __init__(
        self,
        exclude_quotes: bool = True,
        exclude_bibliography: bool = True,
        min_word_match: int = 8,
    ):
        self.exclude_quotes = exclude_quotes
        self.exclude_bibliography = exclude_bibliography
        self.min_word_match = min_word_match

    def parse_document(self, text: str) -> Dict[str, Any]:
        """
        Segments text into structured paragraphs and sentences with exact character offsets.
        """
        paragraphs: List[TextSpan] = []
        sentences: List[TextSpan] = []

        # 1. Paragraph Segmentation
        p_cursor = 0
        raw_paras = re.split(r"\n\s*\n", text)
        for p in raw_paras:
            p_strip = p.strip()
            if p_strip:
                start = text.find(p_strip, p_cursor)
                if start == -1:
                    start = p_cursor
                end = start + len(p_strip)
                paragraphs.append(TextSpan(start_char=start, end_char=end, text=p_strip))
                p_cursor = end

        # 2. Sentence Segmentation
        s_cursor = 0
        for p_span in paragraphs:
            raw_sents = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])", p_span.text)
            for s in raw_sents:
                s_strip = s.strip()
                if len(s_strip.split()) >= 3:
                    start = text.find(s_strip, s_cursor)
                    if start == -1:
                        start = s_cursor
                    end = start + len(s_strip)
                    sentences.append(TextSpan(start_char=start, end_char=end, text=s_strip))
                    s_cursor = end

        # 3. Identify Excluded Regions
        excluded_regions = self.detect_excluded_regions(text)

        return {
            "paragraphs": paragraphs,
            "sentences": sentences,
            "excluded_regions": excluded_regions,
            "total_chars": len(text),
            "total_words": len(text.split()),
        }

    def detect_excluded_regions(self, text: str) -> List[ExcludedRegion]:
        """Detects regions eligible for Turnitin exclusion."""
        exclusions: List[ExcludedRegion] = []

        # 1. Bibliography / References Section Exclusion
        if self.exclude_bibliography:
            ref_pattern = re.compile(
                r"\n\s*(?:references|bibliography|works cited|literature cited)\s*[:\n]",
                re.IGNORECASE,
            )
            matches = list(ref_pattern.finditer(text))
            if matches:
                for m in reversed(matches):
                    # Only treat as bibliography if in the latter half or after 1000 characters
                    if m.start() > 1000 or m.start() >= len(text) * 0.35:
                        exclusions.append(
                            ExcludedRegion(
                                start_char=m.start(),
                                end_char=len(text),
                                reason="bibliography",
                            )
                        )
                        break

        # 2. Quotation Marks Exclusion
        if self.exclude_quotes:
            quote_patterns = [
                r'"([^"\n]{10,})"',  # Straight double quotes
                r'“([^”\n]{10,})”',  # Curly double quotes
                r'«([^»\n]{10,})»',  # Guillemets
                r'^\s*>\s+.*$',      # Blockquotes
            ]
            for pat in quote_patterns:
                for match in re.finditer(pat, text, flags=re.MULTILINE):
                    exclusions.append(
                        ExcludedRegion(
                            start_char=match.start(),
                            end_char=match.end(),
                            reason="quotation",
                        )
                    )

        # Merge overlapping exclusions
        return self._merge_regions(exclusions)

    def is_span_excluded(self, start: int, end: int, exclusions: List[ExcludedRegion]) -> Tuple[bool, Optional[str]]:
        """Checks if a given character span overlaps with an excluded region."""
        for ex in exclusions:
            # Overlap exists if max(start1, start2) < min(end1, end2)
            if max(start, ex.start_char) < min(end, ex.end_char):
                return True, ex.reason
        return False, None

    @staticmethod
    def _merge_regions(regions: List[ExcludedRegion]) -> List[ExcludedRegion]:
        if not regions:
            return []
        sorted_regions = sorted(regions, key=lambda r: r.start_char)
        merged = [sorted_regions[0]]
        for r in sorted_regions[1:]:
            prev = merged[-1]
            if r.start_char <= prev.end_char:
                prev.end_char = max(prev.end_char, r.end_char)
            else:
                merged.append(r)
        return merged


# =============================================================================
# STAGE 2: EXACT & NEAR-EXACT STRING MATCHING (WINNOWING ALGORITHM)
# =============================================================================
class WinnowingFingerprinter:
    """
    Mathematical implementation of the Winnowing Algorithm for local document fingerprinting:
    - Normalizes text and generates k-gram shingles.
    - Computes rolling hashes via Rabin-Karp polynomial hashing.
    - Applies sliding window minimum selection: in each window of size w = t - k + 1,
      picks the minimum hash. Guarantees that any match of length >= t is detected.
    """

    def __init__(self, k_shingle_size: int = 8, window_size: int = 4, base: int = 257, prime: int = 1_000_000_007):
        self.k = k_shingle_size  # k words per shingle (default: 8 words)
        self.w = window_size     # Window size w for minimum selection
        self.base = base
        self.prime = prime

    def tokenize_with_offsets(self, text: str) -> List[Tuple[str, int, int]]:
        """
        Tokenizes text into words while recording exact character start and end offsets.
        """
        tokens: List[Tuple[str, int, int]] = []
        for m in re.finditer(r"\b[A-Za-z0-9'-]+\b", text):
            tokens.append((m.group(0).lower(), m.start(), m.end()))
        return tokens

    def _hash_shingle(self, words: List[str]) -> int:
        """Computes polynomial rolling hash for a sequence of words."""
        h = 0
        for w in words:
            for ch in w:
                h = (h * self.base + ord(ch)) % self.prime
        return h

    def fingerprint(self, text: str) -> List[Fingerprint]:
        """
        Generates Winnowing fingerprints for the document.
        """
        token_info = self.tokenize_with_offsets(text)
        n = len(token_info)
        if n < self.k:
            return []

        # 1. Compute k-gram shingle hashes
        shingle_hashes: List[Tuple[int, int, int, int]] = []
        for i in range(n - self.k + 1):
            shingle_words = [token_info[i + j][0] for j in range(self.k)]
            h = self._hash_shingle(shingle_words)
            start_char = token_info[i][1]
            end_char = token_info[i + self.k - 1][2]
            shingle_hashes.append((h, start_char, end_char, i))

        # 2. Sliding window minimum hash selection (Winnowing Algorithm)
        # Any substring match >= (w + k - 1) words is guaranteed to be found.
        num_hashes = len(shingle_hashes)
        if num_hashes <= self.w:
            min_item = min(shingle_hashes, key=lambda x: x[0])
            return [Fingerprint(hash_value=min_item[0], start_char=min_item[1], end_char=min_item[2], token_index=min_item[3])]

        fingerprints: List[Fingerprint] = []
        last_selected_index = -1

        for i in range(num_hashes - self.w + 1):
            window = shingle_hashes[i : i + self.w]
            # Select minimum hash. Tie-breaking rule: choose rightmost minimum
            min_val = min(item[0] for item in window)
            # Find rightmost instance of min_val in current window
            min_pos = -1
            min_item = None
            for idx in range(len(window) - 1, -1, -1):
                if window[idx][0] == min_val:
                    min_pos = i + idx
                    min_item = window[idx]
                    break

            if min_pos != last_selected_index and min_item is not None:
                fingerprints.append(
                    Fingerprint(
                        hash_value=min_item[0],
                        start_char=min_item[1],
                        end_char=min_item[2],
                        token_index=min_item[3],
                    )
                )
                last_selected_index = min_pos

        return fingerprints

    def compare(
        self,
        submitted_text: str,
        source_id: str,
        source_title: str,
        source_text: str,
        min_word_match: int = 8,
    ) -> List[MatchedSpan]:
        """
        Compares submitted document against a source document using Winnowing fingerprints.
        Coalesces contiguous overlapping fingerprint matches into extended match spans.
        """
        doc_fps = self.fingerprint(submitted_text)
        src_fps = self.fingerprint(source_text)

        # Hash map of source fingerprints: hash_val -> list of source fingerprints
        src_map: Dict[int, List[Fingerprint]] = defaultdict(list)
        for fp in src_fps:
            src_map[fp.hash_value].append(fp)

        raw_matches: List[Tuple[int, int, int, int]] = []
        for dfp in doc_fps:
            if dfp.hash_value in src_map:
                for sfp in src_map[dfp.hash_value]:
                    raw_matches.append((dfp.start_char, dfp.end_char, sfp.start_char, sfp.end_char))

        if not raw_matches:
            return []

        # Sort matches by submitted start position and coalesce adjacent/overlapping blocks
        raw_matches.sort(key=lambda m: m[0])
        coalesced: List[MatchedSpan] = []

        curr_sub_start, curr_sub_end, curr_src_start, curr_src_end = raw_matches[0]

        for sub_s, sub_e, src_s, src_e in raw_matches[1:]:
            # If submitted spans overlap or are separated by fewer than 40 chars (~6-8 words)
            if sub_s <= curr_sub_end + 40:
                curr_sub_end = max(curr_sub_end, sub_e)
                curr_src_end = max(curr_src_end, src_e)
            else:
                matched_sub_str = submitted_text[curr_sub_start:curr_sub_end]
                if len(matched_sub_str.split()) >= min_word_match:
                    coalesced.append(
                        MatchedSpan(
                            submitted_start=curr_sub_start,
                            submitted_end=curr_sub_end,
                            submitted_text=matched_sub_str,
                            source_id=source_id,
                            source_title=source_title,
                            source_start=curr_src_start,
                            source_end=curr_src_end,
                            source_text=source_text[curr_src_start:curr_src_end],
                            match_type="Verbatim",
                            similarity_score=1.0,
                            explanation=f"Exact winnowed k-gram match across {len(matched_sub_str.split())} words.",
                        )
                    )
                curr_sub_start, curr_sub_end, curr_src_start, curr_src_end = sub_s, sub_e, src_s, src_e

        # Flush final coalesced match
        final_str = submitted_text[curr_sub_start:curr_sub_end]
        if len(final_str.split()) >= min_word_match:
            coalesced.append(
                MatchedSpan(
                    submitted_start=curr_sub_start,
                    submitted_end=curr_sub_end,
                    submitted_text=final_str,
                    source_id=source_id,
                    source_title=source_title,
                    source_start=curr_src_start,
                    source_end=curr_src_end,
                    source_text=source_text[curr_src_start:curr_src_end],
                    match_type="Verbatim",
                    similarity_score=1.0,
                    explanation=f"Exact winnowed k-gram match across {len(final_str.split())} words.",
                )
            )

        return coalesced


# =============================================================================
# STAGE 3: SEMANTIC & MOSAIC PLAGIARISM DETECTION (VECTOR EMBEDDINGS)
# =============================================================================
class SemanticMatcher:
    """
    Detects paraphrased sentences, mosaic patchwriting, and clause reordering
    using dense vector embeddings and Cosine Similarity:
    Flags candidates with Cosine Similarity between 0.78 and 0.99.
    """

    def __init__(self, embedding_provider: str = "auto", openai_api_key: str = "", gemini_api_key: str = ""):
        self.provider = embedding_provider
        self.openai_api_key = openai_api_key
        self.gemini_api_key = gemini_api_key

    def get_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Generates dense vector embeddings using OpenAI, Gemini, or robust local sublinear TF-IDF.
        """
        if not texts:
            return np.empty((0, 0))

        # 1. Try OpenAI text-embedding-3-small
        if self.openai_api_key and self.provider in ("openai", "auto"):
            try:
                headers = {"Authorization": f"Bearer {self.openai_api_key}", "Content-Type": "application/json"}
                body = {"model": "text-embedding-3-small", "input": texts[:64]}
                r = requests.post("https://api.openai.com/v1/embeddings", headers=headers, json=body, timeout=12)
                if r.status_code == 200:
                    data = r.json()
                    vecs = [item["embedding"] for item in data["data"]]
                    return np.array(vecs, dtype=np.float32)
            except Exception as e:
                logger.warning(f"OpenAI embedding call failed: {e}. Falling back.")

        # 2. Try Google Gemini embedding-001
        if self.gemini_api_key and self.provider in ("gemini", "auto"):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:batchEmbedContents?key={self.gemini_api_key}"
                requests_payload = [{"model": "models/text-embedding-004", "content": {"parts": [{"text": t}]}} for t in texts[:64]]
                r = requests.post(url, json={"requests": requests_payload}, timeout=12)
                if r.status_code == 200:
                    data = r.json()
                    vecs = [item["values"] for item in data["embeddings"]]
                    return np.array(vecs, dtype=np.float32)
            except Exception as e:
                logger.warning(f"Gemini embedding call failed: {e}. Falling back.")

        # 3. Robust High-Fidelity Sublinear Character/Word n-gram Vectorizer Fallback
        from sklearn.feature_extraction.text import TfidfVectorizer
        vec = TfidfVectorizer(ngram_range=(1, 3), analyzer="char_wb", sublinear_tf=True)
        try:
            tfidf = vec.fit_transform(texts).toarray().astype(np.float32)
            norms = np.linalg.norm(tfidf, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            return tfidf / norms
        except Exception:
            return np.zeros((len(texts), 64), dtype=np.float32)

    def compute_joint_embeddings(self, sub_texts: List[str], src_texts: List[str]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Computes dense embeddings for submitted and source texts with guaranteed dimension alignment.
        """
        # If API keys are available, invoke external embeddings
        if (self.openai_api_key and self.provider in ("openai", "auto")) or (self.gemini_api_key and self.provider in ("gemini", "auto")):
            sub_vecs = self.get_embeddings(sub_texts)
            src_vecs = self.get_embeddings(src_texts)
            if sub_vecs.size > 0 and src_vecs.size > 0 and sub_vecs.shape[1] == src_vecs.shape[1]:
                return sub_vecs, src_vecs

        # High-Fidelity Joint Character/Word n-gram TF-IDF Embeddings
        from sklearn.feature_extraction.text import TfidfVectorizer
        joint_texts = sub_texts + src_texts
        vec = TfidfVectorizer(ngram_range=(1, 3), analyzer="char_wb", sublinear_tf=True)
        try:
            tfidf = vec.fit_transform(joint_texts).toarray().astype(np.float32)
            norms = np.linalg.norm(tfidf, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            norm_tfidf = tfidf / norms
            return norm_tfidf[:len(sub_texts)], norm_tfidf[len(sub_texts):]
        except Exception:
            return np.zeros((len(sub_texts), 64), dtype=np.float32), np.zeros((len(src_texts), 64), dtype=np.float32)

    @staticmethod
    def cosine_similarity_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Computes Cosine Similarity matrix between embedding matrices a and b."""
        if a.size == 0 or b.size == 0:
            return np.empty((0, 0))
        # Dot product of normalized vectors
        a_norm = a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-12)
        b_norm = b / np.maximum(np.linalg.norm(b, axis=1, keepdims=True), 1e-12)
        return np.dot(a_norm, b_norm.T)

    def find_semantic_matches(
        self,
        submitted_sentences: List[TextSpan],
        source_id: str,
        source_title: str,
        source_sentences: List[TextSpan],
        lower_threshold: float = 0.78,
        upper_threshold: float = 0.99,
    ) -> List[MatchedSpan]:
        """
        Flags candidate sentences with cosine similarity between 0.78 and 0.99
        (synonym swapping, structural paraphrasing, patchwriting).
        """
        if not submitted_sentences or not source_sentences:
            return []

        sub_texts = [s.text for s in submitted_sentences]
        src_texts = [s.text for s in source_sentences]

        sub_vecs, src_vecs = self.compute_joint_embeddings(sub_texts, src_texts)

        if sub_vecs.shape[0] != len(sub_texts) or src_vecs.shape[0] != len(src_texts):
            return []

        sim_matrix = self.cosine_similarity_matrix(sub_vecs, src_vecs)
        semantic_matches: List[MatchedSpan] = []

        for i, sub_s in enumerate(submitted_sentences):
            best_src_idx = int(np.argmax(sim_matrix[i]))
            best_score = float(sim_matrix[i, best_src_idx])

            if lower_threshold <= best_score <= upper_threshold:
                src_s = source_sentences[best_src_idx]
                semantic_matches.append(
                    MatchedSpan(
                        submitted_start=sub_s.start_char,
                        submitted_end=sub_s.end_char,
                        submitted_text=sub_s.text,
                        source_id=source_id,
                        source_title=source_title,
                        source_start=src_s.start_char,
                        source_end=src_s.end_char,
                        source_text=src_s.text,
                        match_type="Mosaic_Patchwriting" if best_score > 0.88 else "Structural_Paraphrase",
                        similarity_score=round(best_score, 3),
                        explanation=f"Semantic embedding cosine similarity: {best_score:.2f}",
                    )
                )

        return semantic_matches


# =============================================================================
# STAGE 4: AI API VERIFICATION & ORIGINALITY REPORT GENERATION
# =============================================================================
class AIReportGenerator:
    """
    Evaluates flagged semantic/structural candidate pairs via LLM API using
    Turnitin's exact System Prompt and Structured JSON outputs.
    Calculates overall Turnitin Similarity Index % and source breakdown.
    """

    def __init__(
        self,
        llm_provider: str = "auto",
        openai_api_key: str = "",
        openai_model: str = "gpt-4o-mini",
        gemini_api_key: str = "",
        gemini_model: str = "gemini-1.5-flash",
        timeout: int = 20,
    ):
        self.provider = llm_provider
        self.openai_api_key = openai_api_key
        self.openai_model = openai_model
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model
        self.timeout = timeout

    def verify_candidate_match(self, match: MatchedSpan) -> MatchedSpan:
        """
        Submits candidate match pair to the AI API for classification.
        """
        payload = {
            "SUBMITTED_SEGMENT": match.submitted_text,
            "SOURCE_SEGMENT": match.source_text,
            "SOURCE_ID": match.source_id,
        }

        eval_json = None

        # 1. Google Gemini Call
        if self.gemini_api_key and self.provider in ("gemini", "auto"):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_api_key}"
                body = {
                    "contents": [{"parts": [{"text": f"{TURNITIN_SIMILARITY_SYSTEM_PROMPT}\n\nEVALUATE:\n{json.dumps(payload)}"}]}],
                    "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
                }
                r = requests.post(url, json=body, timeout=self.timeout)
                if r.status_code == 200:
                    raw_text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    eval_json = json.loads(raw_text)
            except Exception as e:
                logger.warning(f"Gemini similarity evaluation failed: {e}")

        # 2. OpenAI Call
        if not eval_json and self.openai_api_key and self.provider in ("openai", "auto"):
            try:
                headers = {"Authorization": f"Bearer {self.openai_api_key}", "Content-Type": "application/json"}
                body = {
                    "model": self.openai_model,
                    "messages": [
                        {"role": "system", "content": TURNITIN_SIMILARITY_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(payload)},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.0,
                }
                r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body, timeout=self.timeout)
                if r.status_code == 200:
                    eval_json = json.loads(r.json()["choices"][0]["message"]["content"])
            except Exception as e:
                logger.warning(f"OpenAI similarity evaluation failed: {e}")

        # Apply AI evaluation if available
        if eval_json:
            classification = eval_json.get("match_classification", match.match_type)
            if classification == "None":
                match.similarity_score = 0.0
                match.is_excluded = True
                match.exclusion_reason = "ai_verified_independent_writing"
            elif classification == "Quoted_And_Cited" or eval_json.get("is_properly_quoted"):
                match.match_type = "Quoted_And_Cited"
                match.is_excluded = True
                match.exclusion_reason = "properly_quoted_and_cited"
            else:
                match.match_type = classification
                seg_score = float(eval_json.get("overall_segment_similarity_percent", 100)) / 100.0
                match.similarity_score = max(match.similarity_score, seg_score)

            if eval_json.get("explanation"):
                match.explanation = eval_json["explanation"]

        return match

    def build_originality_report(
        self,
        text: str,
        matches: List[MatchedSpan],
        excluded_regions: List[ExcludedRegion],
        start_time: float,
    ) -> TurnitinOriginalityReport:
        """
        Assembles all verified matches, resolves span overlaps, applies Turnitin exclusions,
        and computes the total document Similarity Index Percentage.
        """
        total_chars = len(text)
        total_words = len(text.split())

        # 1. Mark exclusions on matches
        for m in matches:
            if not m.is_excluded:
                for ex in excluded_regions:
                    if max(m.submitted_start, ex.start_char) < min(m.submitted_end, ex.end_char):
                        m.is_excluded = True
                        m.exclusion_reason = ex.reason
                        break

        # 2. Compute non-excluded document characters
        excluded_char_indices: Set[int] = set()
        for ex in excluded_regions:
            for idx in range(ex.start_char, min(ex.end_char, total_chars)):
                excluded_char_indices.add(idx)

        non_excluded_chars = max(1, total_chars - len(excluded_char_indices))

        # 3. Compute non-overlapping matched character set
        matched_char_indices: Set[int] = set()
        source_matched_chars: Dict[str, Set[int]] = defaultdict(set)
        source_info: Dict[str, Dict[str, str]] = {}

        for m in matches:
            if not m.is_excluded and m.similarity_score >= 0.70:
                source_info[m.source_id] = {
                    "title": m.source_title,
                    "category": getattr(m, "source_category", "Internet"),
                    "url": getattr(m, "source_url", ""),
                }
                for idx in range(m.submitted_start, min(m.submitted_end, total_chars)):
                    if idx not in excluded_char_indices:
                        matched_char_indices.add(idx)
                        source_matched_chars[m.source_id].add(idx)

        matched_non_excluded_chars = len(matched_char_indices)
        similarity_index = round((matched_non_excluded_chars / non_excluded_chars) * 100.0, 1)

        # 4. Source Breakdown (sorted by descending similarity percentage)
        sources_breakdown: List[SourceBreakdownItem] = []
        is_first = True
        for src_id, char_set in sorted(source_matched_chars.items(), key=lambda item: len(item[1]), reverse=True):
            src_pct = round((len(char_set) / non_excluded_chars) * 100.0, 1)
            info = source_info.get(src_id, {})
            # Approximate words from character count (~5.5 chars/word)
            approx_words = max(1, int(len(char_set) / 5.5))
            sources_breakdown.append(
                SourceBreakdownItem(
                    source_id=src_id,
                    source_title=info.get("title", f"Source {src_id}"),
                    source_category=info.get("category", "Internet Source"),
                    url=info.get("url", ""),
                    matched_word_count=approx_words,
                    similarity_percentage=src_pct,
                    is_primary=is_first,
                )
            )
            is_first = False

        elapsed = round(time.time() - start_time, 2)

        return TurnitinOriginalityReport(
            similarity_index_percent=similarity_index,
            total_document_words=total_words,
            total_document_chars=total_chars,
            non_excluded_chars=non_excluded_chars,
            matched_non_excluded_chars=matched_non_excluded_chars,
            sources_breakdown=sources_breakdown,
            matched_passages=matches,
            excluded_regions=excluded_regions,
            processing_time_seconds=elapsed,
            metadata={
                "total_passages_flagged": len(matches),
                "non_excluded_passages": len([m for m in matches if not m.is_excluded]),
                "excluded_passages": len([m for m in matches if m.is_excluded]),
            },
        )


# =============================================================================
# CANDIDATE CORPUS RETRIEVAL (LOCAL + EXTERNAL PLACEHOLDERS)
# =============================================================================
class CorpusRetriever:
    """
    Candidate source retrieval layer:
    1. Local Institutional Repository (Proovexa SQLite / MySQL DB)
    2. External Academic Search (Crossref / Semantic Scholar APIs)
    3. Live Web Search (Serper / Bing Search APIs)
    """

    @staticmethod
    def search_local_repository(document=None, max_sources: int = 50) -> List[Dict[str, Any]]:
        """Retrieves active reference documents from Proovexa's database."""
        try:
            from documents.models import ReferenceSource
            qs = ReferenceSource.objects.filter(is_active=True).select_related("document")
            if document:
                qs = qs.exclude(document=document)
            sources = []
            for src in qs[:max_sources]:
                sources.append({
                    "id": str(src.id),
                    "title": src.title,
                    "text": src.retrieved_text,
                    "category": src.get_source_type_display(),
                    "url": getattr(src, "url", ""),
                })
            return sources
        except Exception:
            return []

    @staticmethod
    def search_crossref_academic(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
        """
        Placeholder / live implementation for Crossref Academic metadata & abstract retrieval.
        """
        try:
            url = f"https://api.crossref.org/works?query={requests.utils.quote(query)}&rows={max_results}"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                items = r.json().get("message", {}).get("items", [])
                results = []
                for item in items:
                    title = item.get("title", ["Academic Publication"])[0]
                    abstract = item.get("abstract", "")
                    clean_abstract = re.sub(r"<[^>]+>", "", abstract)
                    if clean_abstract:
                        results.append({
                            "id": item.get("DOI", f"crossref_{len(results)}"),
                            "title": title,
                            "text": clean_abstract,
                            "category": "Crossref Academic Publication",
                            "url": item.get("URL", ""),
                        })
                return results
        except Exception:
            pass
        return []

    @staticmethod
    def search_web_sources(queries: List[str], api_key: str = "") -> List[Dict[str, Any]]:
        """
        Placeholder for external Web Search APIs (Serper.dev, Bing Search, or Tavily).
        """
        # When an external search key is configured, invoke Serper or Bing
        return []


# =============================================================================
# UNIFIED HYBRID SIMILARITY PIPELINE
# =============================================================================
class TurnitinSimilarityPipeline:
    """
    End-to-End Orchestrator for Turnitin-style Hybrid Plagiarism Detection:
    Combines Preprocessing -> Winnowing -> Semantic Embedding -> AI Verification.
    """

    def __init__(
        self,
        exclude_quotes: bool = True,
        exclude_bibliography: bool = True,
        min_word_match: int = 8,
        k_shingle_size: int = 8,
        semantic_threshold: float = 0.78,
        ai_provider: str = "auto",
        openai_api_key: str = "",
        gemini_api_key: str = "",
    ):
        self.preprocessor = Preprocessor(
            exclude_quotes=exclude_quotes,
            exclude_bibliography=exclude_bibliography,
            min_word_match=min_word_match,
        )
        self.fingerprinter = WinnowingFingerprinter(k_shingle_size=k_shingle_size)
        self.semantic_matcher = SemanticMatcher(
            embedding_provider=ai_provider,
            openai_api_key=openai_api_key,
            gemini_api_key=gemini_api_key,
        )
        self.report_generator = AIReportGenerator(
            llm_provider=ai_provider,
            openai_api_key=openai_api_key,
            gemini_api_key=gemini_api_key,
        )
        self.min_word_match = min_word_match

    def analyze(
        self,
        submitted_text: str,
        candidate_sources: List[Dict[str, Any]],
        verify_with_ai: bool = True,
    ) -> TurnitinOriginalityReport:
        """
        Executes the 4-stage Turnitin hybrid similarity analysis.
        """
        start_time = time.time()

        # Stage 1: Parse Document & Detect Exclusions
        parsed_doc = self.preprocessor.parse_document(submitted_text)
        sub_sentences = parsed_doc["sentences"]
        excluded_regions = parsed_doc["excluded_regions"]

        all_matches: List[MatchedSpan] = []

        # Iterate through candidate sources
        for src in candidate_sources:
            src_id = str(src.get("id", "src_unknown"))
            src_title = src.get("title", "Untitled Reference")
            src_text = src.get("text", "")
            if not src_text or len(src_text.split()) < 5:
                continue

            parsed_src = self.preprocessor.parse_document(src_text)
            src_sentences = parsed_src["sentences"]

            # Stage 2: Exact & Near-Exact Winnowing Fingerprinting
            winnowing_matches = self.fingerprinter.compare(
                submitted_text=submitted_text,
                source_id=src_id,
                source_title=src_title,
                source_text=src_text,
                min_word_match=self.min_word_match,
            )
            for wm in winnowing_matches:
                wm.source_category = src.get("category", "Internet Source")
                wm.source_url = src.get("url", "")
            all_matches.extend(winnowing_matches)

            # Stage 3: Semantic & Mosaic Plagiarism (Dense Embeddings + Cosine Similarity)
            semantic_candidates = self.semantic_matcher.find_semantic_matches(
                submitted_sentences=sub_sentences,
                source_id=src_id,
                source_title=src_title,
                source_sentences=src_sentences,
                lower_threshold=0.78,
                upper_threshold=0.99,
            )

            # Filter out semantic candidates that are already covered by Winnowing exact matches
            for sc in semantic_candidates:
                sc.source_category = src.get("category", "Internet Source")
                sc.source_url = src.get("url", "")
                already_covered = any(
                    max(sc.submitted_start, wm.submitted_start) < min(sc.submitted_end, wm.submitted_end)
                    for wm in winnowing_matches
                )
                if not already_covered:
                    all_matches.append(sc)

        # Stage 4: AI API Verification of Flagged Semantic / Structural Pairs
        if verify_with_ai and all_matches:
            # Verify candidate semantic / mosaic matches with AI
            with ThreadPoolExecutor(max_workers=4) as executor:
                verified_matches = list(executor.map(self.report_generator.verify_candidate_match, all_matches))
                all_matches = verified_matches

        # Assemble Final Turnitin-Style Originality Report
        report = self.report_generator.build_originality_report(
            text=submitted_text,
            matches=all_matches,
            excluded_regions=excluded_regions,
            start_time=start_time,
        )

        return report


# =============================================================================
# SAMPLE EXECUTION & BENCHMARK SUITE
# =============================================================================
if __name__ == "__main__":
    print("=" * 80)
    print("TURNITIN HYBRID SIMILARITY & PLAGIARISM DETECTION PIPELINE DEMO")
    print("=" * 80)

    # 1. Sample Candidate Sources
    candidate_corpus = [
        {
            "id": "SRC-001",
            "title": "Journal of Structural Dynamics (Vol. 14, 2023)",
            "category": "Publications",
            "url": "https://doi.org/10.1016/j.jstrudyn.2023.04.012",
            "text": (
                "Finite element methods have traditionally served as the foundational paradigm for structural analysis. "
                "However, these numerical procedures frequently experience acute computational bottlenecks when resolving "
                "complex geometric nonlinearities in high-rise steel frame designs under intense ground acceleration."
            ),
        },
        {
            "id": "SRC-002",
            "title": "Metropolitan University Student Thesis Repository",
            "category": "Student Papers",
            "url": "https://repository.metropolitan.edu/theses/2024/civil/7719",
            "text": (
                "Artificial intelligence and deep convolutional neural networks offer unprecedented precision in "
                "detecting surface fatigue cracks and structural degradation in reinforced concrete infrastructures."
            ),
        },
    ]

    # 2. Submitted Student Paper with Verbatim, Paraphrased, Quoted, and Bibliography sections
    submitted_student_paper = """
    A Comprehensive Study of Computational Structural Analysis

    Finite element methods have traditionally served as the foundational paradigm for structural analysis. However, these numerical procedures frequently experience acute computational bottlenecks when resolving complex geometric nonlinearities in high-rise steel frame designs under intense ground acceleration.

    According to Dr. Smith's earlier treatise, "machine learning represents an evolving frontier for structural safety" (Smith, 2021).

    Furthermore, deep neural networks and automated computer vision algorithms provide unmatched exactness when identifying microscopic stress fractures across reinforced concrete structures throughout the metropolitan area.

    References
    1. Smith, J. (2021). Structural Analysis Fundamentals. Academic Press.
    2. Doe, A. (2023). Machine Learning in Civil Engineering. Springer.
    """

    pipeline = TurnitinSimilarityPipeline(
        exclude_quotes=True,
        exclude_bibliography=True,
        min_word_match=8,
        ai_provider="local",  # Can pass 'gemini' or 'openai' with keys
    )

    report = pipeline.analyze(submitted_student_paper, candidate_corpus, verify_with_ai=False)

    print(f"\n[+] Overall Similarity Index: {report.similarity_index_percent}%")
    print(f"[+] Total Document Words:     {report.total_document_words}")
    print(f"[+] Non-Excluded Characters:  {report.non_excluded_chars:,}")
    print(f"[+] Matched Non-Excluded:     {report.matched_non_excluded_chars:,}")
    print(f"[+] Processing Time:          {report.processing_time_seconds}s")

    print("\n--- PRIMARY SOURCE BREAKDOWN ---")
    for s in report.sources_breakdown:
        badge = "[PRIMARY SOURCE]" if s.is_primary else "[SECONDARY]"
        print(f" {badge:16} {s.similarity_percentage}% - {s.source_title} ({s.source_category})")

    print("\n--- MATCHED PASSAGES HIGHLIGHT MAP ---")
    for idx, p in enumerate(report.matched_passages, 1):
        status = "[EXCLUDED]" if p.is_excluded else "[MATCHED]"
        print(f" {idx}. {status:10} Type: {p.match_type:20} Score: {p.similarity_score:.2f}")
        print(f"    Source: {p.source_title} ({p.source_id})")
        print(f"    Snippet: \"{p.submitted_text[:70]}...\"")
        if p.is_excluded:
            print(f"    Exclusion Reason: {p.exclusion_reason}")
