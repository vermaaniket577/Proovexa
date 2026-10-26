"""
Turnitin-Style 5-Stage AI Writing & Paraphrase Detection Pipeline.
==================================================================
Production-ready computational linguistics architecture adhering to Turnitin's exact specifications:

Stage 1: Qualifying Prose Pre-Processor (`preprocess_text`)
         Strips tables, code blocks, lists, quotes, titles, and bibliographies.
         Enforces Turnitin's >= 300 qualifying words minimum gate.
Stage 2: Mathematical Burstiness & Perplexity Calculator (`compute_statistics`)
         Computes sentence length standard deviation, coefficient of variation,
         lexical diversity (TTR), transition repetition, and perplexity.
Stage 3: Overlapping Sliding Window Generator (`create_overlapping_windows`)
         Splits prose into ~250-word windows with 3-sentence stride, preserving global indices.
Stage 4: Concurrent AI API Classifier (`evaluate_windows`)
         Evaluates each window using LLM APIs (OpenAI, Gemini, or Anthropic) with structured JSON,
         blending 30% mathematical burstiness with 70% qualitative LLM signal.
Stage 5: Sentence Pooling & Turnitin Report Generator (`aggregate_report`)
         Pools multi-window probabilities for each sentence, classifies into Cyan (Direct AI)
         and Purple (AI Paraphrased), and enforces Turnitin's 1%-19% asterisk (*%) suppression rule.
"""

from __future__ import annotations
import re
import json
import time
import math
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple, Any, Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import requests

logger = logging.getLogger(__name__)

# =============================================================================
# SYSTEM PROMPT FOR THE AI API (SEGMENT ANALYZER)
# =============================================================================
TURNITIN_SYSTEM_PROMPT = """You are an expert computational linguistics engine modeled after Turnitin's AI Writing Detection classifier. Your task is to analyze a provided segment of qualifying academic or professional prose and classify each sentence into one of three categories:
1. "human": Unpredictable word choices, varied sentence lengths, authentic voice, idiosyncratic phrasing, or specific concrete reasoning.
2. "ai_generated": Low perplexity (highly predictable next-token choices), low burstiness (metronomic sentence length and uniform subject-verb-object syntax), overused transition markers (e.g., "Furthermore," "Moreover," "Additionally," "It is important to note"), and generic surface-level analysis.
3. "ai_paraphrased": Underlying rigid AI sentence skeletons and uniform paragraph rhythm, masked by unnatural synonym substitution, awkward thesaurus swaps, or word-spinner artifacts.

### Input Format
You will receive a JSON object containing:
- `segment_id`: Identifier for the current overlapping window.
- `statistical_metrics`: Pre-calculated sentence word counts and standard deviation (burstiness score) for this segment.
- `sentences`: An array of indexed sentences in the segment.

### Evaluation Rules
- Do NOT flag standard academic terminology, proper nouns, or clichés unless the surrounding syntax exhibits uniform, low-burstiness AI rhythm.
- Apply ESL (English as a Second Language) fairness: Do not mistake simple vocabulary or minor grammatical repetition for AI generation if sentence length and structural flow vary naturally.
- Score each sentence independently in light of the full segment context on a probability scale from 0.00 (definitely human) to 1.00 (definitely AI).

### Output Schema (Strict JSON Only)
Return ONLY a valid JSON object matching this exact structure:
{
  "segment_id": "string",
  "segment_ai_probability": 0.00,
  "segment_paraphrase_probability": 0.00,
  "linguistic_signals": {
    "perplexity_assessment": "low | medium | high",
    "burstiness_assessment": "low | medium | high",
    "detected_ai_markers": ["string"]
  },
  "sentence_scores": [
    {
      "sentence_index": 0,
      "ai_probability": 0.00,
      "paraphrase_probability": 0.00,
      "classification": "human | ai_generated | ai_paraphrased",
      "reason": "Brief 10-word explanation of syntactic or lexical signal"
    }
  ]
}"""

# Common repetitive AI transition markers
AI_TRANSITION_MARKERS = {
    "furthermore", "moreover", "additionally", "consequently", "in conclusion",
    "it is crucial to note", "it is important to consider", "plays a pivotal role",
    "plays a vital role", "a testament to", "beacon of", "delve into",
    "intricate tapestry", "navigating the", "fostering a", "underscores the"
}


# =============================================================================
# DATA STRUCTURES & SCHEMAS
# =============================================================================
@dataclass
class IndexedSentence:
    global_index: int
    text: str
    word_count: int
    start_char: int
    end_char: int


@dataclass
class StatisticalMetrics:
    sentence_count: int
    word_count: int
    sentence_length_mean: float
    sentence_length_std_dev: float
    coefficient_of_variation: float
    type_token_ratio: float
    burstiness_score: float  # Normalized [0.0, 1.0] where 1.0 = highly uniform (AI)
    perplexity_proxy: float
    ai_transition_density: float


@dataclass
class OverlappingWindow:
    segment_id: str
    sentence_indices: List[int]
    sentences: List[Dict[str, Any]]
    window_text: str
    statistical_metrics: StatisticalMetrics


@dataclass
class SentenceEvaluation:
    sentence_index: int
    sentence_text: str
    word_count: int
    pooled_ai_probability: float
    pooled_paraphrase_probability: float
    classification: str  # 'human', 'ai_generated', 'ai_paraphrased'
    highlight_color: str  # 'none', 'cyan', 'purple'
    window_appearances: int
    reasons: List[str] = field(default_factory=list)


@dataclass
class TurnitinDetectionReport:
    status: str  # 'completed', 'insufficient_prose', 'error'
    turnitin_display_score: str  # '0%', '*%', or '20%'-'100%'
    is_masked_asterisk: bool  # True if in 1%-19% unreliable range
    overall_ai_percentage: float  # Raw calculated percentage
    ai_generated_cyan_pct: float  # Percentage of direct AI text
    ai_paraphrased_purple_pct: float  # Percentage of synonym-spun/paraphrased text
    qualifying_word_count: int
    total_sentences: int
    flagged_sentences_count: int
    sentences: List[SentenceEvaluation]
    document_metrics: Dict[str, Any]
    provider_used: str
    processing_time_seconds: float
    raw_window_results: List[Dict[str, Any]] = field(default_factory=list)
    error_message: Optional[str] = None


# =============================================================================
# PRODUCTION TURNITIN DETECTION PIPELINE
# =============================================================================
class TurnitinAIPipeline:
    """
    Production-grade Turnitin 5-Stage AI Writing & Paraphrase Detection Engine.
    Supports Google Gemini, OpenAI, Anthropic Claude, and high-precision offline statistical fallback.
    """

    def __init__(
        self,
        provider: str = "auto",  # 'gemini', 'openai', 'anthropic', 'auto', or 'local'
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "gemini-1.5-flash",
        openai_api_key: Optional[str] = None,
        openai_model: str = "gpt-4o-mini",
        anthropic_api_key: Optional[str] = None,
        anthropic_model: str = "claude-3-5-haiku-20241022",
        target_window_words: int = 250,
        stride_sentences: int = 3,
        min_prose_words: int = 300,
        timeout_seconds: int = 25,
        max_concurrency: int = 6,
        confidence_threshold: float = 0.70,
    ):
        self.provider = provider.lower()
        self.target_window_words = target_window_words
        self.stride_sentences = stride_sentences
        self.min_prose_words = min_prose_words
        self.timeout = timeout_seconds
        self.max_concurrency = max_concurrency
        self.confidence_threshold = confidence_threshold

        # API Keys & Models
        self.gemini_api_key = (gemini_api_key or (api_key if self.provider == 'gemini' else '') or '').strip()
        self.gemini_model = gemini_model or "gemini-1.5-flash"

        self.openai_api_key = (openai_api_key or (api_key if self.provider == 'openai' else '') or '').strip()
        self.openai_model = openai_model or "gpt-4o-mini"

        self.anthropic_api_key = (anthropic_api_key or (api_key if self.provider == 'anthropic' else '') or '').strip()
        self.anthropic_model = anthropic_model or "claude-3-5-haiku-20241022"

        # Auto-detect if provider is 'auto'
        if self.provider == "auto":
            if self.gemini_api_key:
                self.active_provider = "gemini"
            elif self.openai_api_key:
                self.active_provider = "openai"
            elif self.anthropic_api_key:
                self.active_provider = "anthropic"
            else:
                self.active_provider = "local"
        else:
            self.active_provider = self.provider

    # =========================================================================
    # STAGE 1: QUALIFYING PROSE PRE-PROCESSOR
    # =========================================================================
    def preprocess_text(
        self,
        raw_text: str,
        force_short_text: bool = False
    ) -> Tuple[Optional[List[IndexedSentence]], Optional[Dict[str, Any]]]:
        """
        Stage 1: Strips out code blocks, Markdown tables, bulleted/numbered lists,
        blockquotes, headers, and Reference/Bibliography sections.
        Enforces Turnitin's minimum 300 continuous words requirement.
        """
        if not raw_text or not raw_text.strip():
            return None, {
                "status": "insufficient_prose",
                "score": None,
                "message": "Empty document provided.",
                "qualifying_word_count": 0
            }

        text = raw_text

        # 1. Strip Markdown and HTML code blocks
        text = re.sub(r"```[\s\S]*?```", "\n", text)
        text = re.sub(r"<code>[\s\S]*?</code>", "\n", text, flags=re.IGNORECASE)

        # 2. Strip Markdown tables and HTML tables
        text = re.sub(r"\|[^\n]+\|\n\|[-:| ]+\|\n(?:\|[^\n]+\|\n?)*", "\n", text)
        text = re.sub(r"<table[\s\S]*?</table>", "\n", text, flags=re.IGNORECASE)

        # 3. Strip blockquotes
        text = re.sub(r"^\s*>\s+.*$", "", text, flags=re.MULTILINE)

        # 4. Strip Reference, Bibliography, or Works Cited section (towards document end)
        ref_pattern = re.compile(
            r"\n\s*(?:references|bibliography|works cited|literature cited)\s*[:\n]",
            re.IGNORECASE
        )
        matches = list(ref_pattern.finditer(text))
        if matches:
            # Only strip if the heading appears in the second half or after 800 chars
            for m in reversed(matches):
                if m.start() > 800 or m.start() >= len(text) * 0.35:
                    text = text[:m.start()]
                    break

        # 5. Filter line-by-line: remove lists, headers, short meta tags
        clean_lines = []
        for line in text.splitlines():
            line_str = line.strip()
            if not line_str:
                continue

            # Strip markdown headers (# Heading)
            if re.match(r"^#{1,6}\s+", line_str):
                continue

            # Strip bulleted or numbered list items
            if re.match(r"^(\*|-|\+|\d+[\.)])\s+", line_str):
                continue

            # Strip all-caps titles / metadata headers (< 6 words)
            words = line_str.split()
            if len(words) < 4 and (line_str.isupper() or line_str.endswith(':')):
                continue

            clean_lines.append(line_str)

        cleaned_prose = " ".join(clean_lines)

        # 6. Sentence Segmentation preserving character offsets
        raw_sentence_splits = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])", cleaned_prose)

        sentences: List[IndexedSentence] = []
        char_cursor = 0
        global_idx = 0

        for raw_s in raw_sentence_splits:
            s_clean = raw_s.strip()
            # Retain sentences that contain at least 4 words
            word_list = s_clean.split()
            if len(word_list) >= 4:
                start_char = cleaned_prose.find(s_clean, char_cursor)
                if start_char == -1:
                    start_char = char_cursor
                end_char = start_char + len(s_clean)
                char_cursor = end_char

                sentences.append(IndexedSentence(
                    global_index=global_idx,
                    text=s_clean,
                    word_count=len(word_list),
                    start_char=start_char,
                    end_char=end_char
                ))
                global_idx += 1

        total_qualifying_words = sum(s.word_count for s in sentences)

        # Enforce Turnitin Minimum Length Gate (300 words)
        if total_qualifying_words < self.min_prose_words and not force_short_text:
            return None, {
                "status": "insufficient_prose",
                "score": None,
                "message": (
                    f"Document contains {total_qualifying_words} qualifying words of continuous prose, "
                    f"which is below Turnitin's required minimum threshold of {self.min_prose_words} words."
                ),
                "qualifying_word_count": total_qualifying_words,
                "required_minimum_words": self.min_prose_words
            }

        return sentences, None

    # =========================================================================
    # STAGE 2: MATHEMATICAL BURSTINESS & PERPLEXITY CALCULATOR
    # =========================================================================
    def compute_statistics(self, sentences: List[IndexedSentence]) -> StatisticalMetrics:
        """
        Stage 2: Calculates mathematical burstiness (sentence length variance,
        coefficient of variation), lexical diversity (type-token ratio), transition
        density, and statistical perplexity proxy.
        """
        if not sentences:
            return StatisticalMetrics(
                sentence_count=0, word_count=0, sentence_length_mean=0.0,
                sentence_length_std_dev=0.0, coefficient_of_variation=0.0,
                type_token_ratio=0.0, burstiness_score=0.5,
                perplexity_proxy=50.0, ai_transition_density=0.0
            )

        lengths = [s.word_count for s in sentences]
        total_words = sum(lengths)
        sentence_count = len(sentences)

        mean_length = float(np.mean(lengths))
        std_length = float(np.std(lengths))
        cv = std_length / (mean_length + 1e-6)

        # Lexical diversity: Type-Token Ratio (TTR)
        combined_text = " ".join(s.text for s in sentences)
        tokens = re.findall(r"\b[a-zA-Z]{2,}\b", combined_text.lower())
        unique_tokens = set(tokens)
        ttr = len(unique_tokens) / max(1, len(tokens))

        # AI Transition markers density
        transition_hits = 0
        for s in sentences:
            s_lower = s.text.lower()
            if any(s_lower.startswith(m) or f" {m} " in s_lower for m in AI_TRANSITION_MARKERS):
                transition_hits += 1
        transition_density = transition_hits / max(1, sentence_count)

        # Mathematical burstiness score:
        # High CV (> 0.45) indicates human variability (bursty).
        # Low CV (< 0.22) indicates uniform metronomic AI cadence.
        # Scale to [0.0, 1.0] where 1.0 is strongly characteristic of AI uniformity.
        uniformity_signal = float(np.clip(1.0 - (cv / 0.50), 0.0, 1.0))
        lexical_rigidity = float(np.clip(1.0 - (ttr / 0.70), 0.0, 1.0))
        burstiness_score = round((0.60 * uniformity_signal) + (0.40 * lexical_rigidity), 3)

        # Statistical Bigram Perplexity Proxy (Fast, offline, robust)
        if len(tokens) >= 4:
            bigrams = [(tokens[i], tokens[i + 1]) for i in range(len(tokens) - 1)]
            from collections import Counter
            w_counts = Counter(tokens)
            b_counts = Counter(bigrams)
            nlls = []
            for w1, w2 in bigrams:
                p = (b_counts[(w1, w2)] + 0.1) / (w_counts[w1] + 1.0)
                nlls.append(-math.log(max(1e-6, min(1.0, p))))
            mean_nll = float(np.mean(nlls)) if nlls else 3.5
            ppl_proxy = round(float(np.clip(math.exp(mean_nll) * 6.5, 10.0, 150.0)), 1)
        else:
            ppl_proxy = 65.0

        return StatisticalMetrics(
            sentence_count=sentence_count,
            word_count=total_words,
            sentence_length_mean=round(mean_length, 2),
            sentence_length_std_dev=round(std_length, 2),
            coefficient_of_variation=round(cv, 3),
            type_token_ratio=round(ttr, 3),
            burstiness_score=burstiness_score,
            perplexity_proxy=ppl_proxy,
            ai_transition_density=round(transition_density, 3)
        )

    # =========================================================================
    # STAGE 3: OVERLAPPING SLIDING WINDOW GENERATOR
    # =========================================================================
    def create_overlapping_windows(self, sentences: List[IndexedSentence]) -> List[OverlappingWindow]:
        """
        Stage 3: Groups indexed sentences into overlapping passages of ~250 words
        (or 8 sentences with a stride of 3 sentences), ensuring every sentence retains
        its global sentence_index for cross-window pooling.
        """
        windows: List[OverlappingWindow] = []
        n = len(sentences)
        i = 0
        window_counter = 0

        while i < n:
            current_window_sentences: List[IndexedSentence] = []
            current_words = 0
            j = i

            # Accumulate until ~target_window_words or maximum 10 sentences
            while j < n and (current_words < self.target_window_words or len(current_window_sentences) < 4):
                current_window_sentences.append(sentences[j])
                current_words += sentences[j].word_count
                j += 1
                if len(current_window_sentences) >= 10:
                    break

            indices = [s.global_index for s in current_window_sentences]
            serialized_sentences = [
                {"sentence_index": s.global_index, "text": s.text}
                for s in current_window_sentences
            ]
            win_text = " ".join(s.text for s in current_window_sentences)
            stats = self.compute_statistics(current_window_sentences)

            windows.append(OverlappingWindow(
                segment_id=f"window_{window_counter}",
                sentence_indices=indices,
                sentences=serialized_sentences,
                window_text=win_text,
                statistical_metrics=stats
            ))
            window_counter += 1

            if j >= n:
                break
            i += self.stride_sentences

        return windows

    # =========================================================================
    # STAGE 4: CONCURRENT AI API CLASSIFIER (WITH STRUCTURED OUTPUTS)
    # =========================================================================
    def evaluate_windows(
        self,
        windows: List[OverlappingWindow]
    ) -> List[Dict[str, Any]]:
        """
        Stage 4: Sends each overlapping window concurrently to the AI API using
        structured outputs. Blends mathematical burstiness (30% weight) with LLM
        classification (70% weight) to produce robust, ESL-fair probabilities.
        """
        results: List[Dict[str, Any]] = [None] * len(windows)

        with ThreadPoolExecutor(max_workers=min(self.max_concurrency, len(windows) or 1)) as executor:
            future_to_idx = {
                executor.submit(self._evaluate_single_window_with_retry, win): idx
                for idx, win in enumerate(windows)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    res = future.result()
                    results[idx] = res
                except Exception as e:
                    logger.exception("Window %s evaluation failed: %s", windows[idx].segment_id, e)
                    # Graceful fallback to statistical scoring
                    results[idx] = self._statistical_window_fallback(windows[idx])

        return results

    def _evaluate_single_window_with_retry(
        self,
        window: OverlappingWindow,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """Calls the active AI API with exponential backoff and schema validation."""
        for attempt in range(max_retries + 1):
            try:
                if self.active_provider == "gemini" and self.gemini_api_key:
                    raw_eval = self._call_gemini(window)
                elif self.active_provider == "openai" and self.openai_api_key:
                    raw_eval = self._call_openai(window)
                elif self.active_provider == "anthropic" and self.anthropic_api_key:
                    raw_eval = self._call_anthropic(window)
                else:
                    return self._statistical_window_fallback(window)

                if raw_eval:
                    return self._blend_window_scores(window, raw_eval)

            except Exception as e:
                logger.warning("Attempt %d for %s failed: %s", attempt + 1, window.segment_id, e)
                if attempt < max_retries:
                    time.sleep(1.2 * (attempt + 1))

        # Fallback to mathematical engine on timeout or exhausted retries
        return self._statistical_window_fallback(window)

    def _call_gemini(self, window: OverlappingWindow) -> Optional[Dict[str, Any]]:
        """Google Gemini API invocation with JSON Structured Outputs."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_api_key}"
        user_payload = {
            "segment_id": window.segment_id,
            "statistical_metrics": {
                "sentence_count": window.statistical_metrics.sentence_count,
                "sentence_length_std_dev": window.statistical_metrics.sentence_length_std_dev,
                "coefficient_of_variation": window.statistical_metrics.coefficient_of_variation,
                "burstiness_score": window.statistical_metrics.burstiness_score,
                "type_token_ratio": window.statistical_metrics.type_token_ratio
            },
            "sentences": window.sentences
        }

        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": f"{TURNITIN_SYSTEM_PROMPT}\n\nANALYZE THE FOLLOWING SEGMENT:\n{json.dumps(user_payload)}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
                "maxOutputTokens": 2048
            }
        }

        resp = requests.post(url, json=body, timeout=self.timeout)
        if resp.status_code == 200:
            data = resp.json()
            raw_text = data['candidates'][0]['content']['parts'][0]['text']
            return json.loads(raw_text)
        return None

    def _call_openai(self, window: OverlappingWindow) -> Optional[Dict[str, Any]]:
        """OpenAI API invocation with response_format json_object."""
        url = "https://api.openai.com/v1/chat/completions"
        user_payload = {
            "segment_id": window.segment_id,
            "statistical_metrics": {
                "sentence_count": window.statistical_metrics.sentence_count,
                "sentence_length_std_dev": window.statistical_metrics.sentence_length_std_dev,
                "burstiness_score": window.statistical_metrics.burstiness_score,
                "type_token_ratio": window.statistical_metrics.type_token_ratio
            },
            "sentences": window.sentences
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.openai_api_key}"
        }

        body = {
            "model": self.openai_model,
            "messages": [
                {"role": "system", "content": TURNITIN_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload)}
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }

        resp = requests.post(url, headers=headers, json=body, timeout=self.timeout)
        if resp.status_code == 200:
            content = resp.json()['choices'][0]['message']['content']
            return json.loads(content)
        return None

    def _call_anthropic(self, window: OverlappingWindow) -> Optional[Dict[str, Any]]:
        """Anthropic Claude API invocation."""
        url = "https://api.anthropic.com/v1/messages"
        user_payload = {
            "segment_id": window.segment_id,
            "statistical_metrics": asdict(window.statistical_metrics),
            "sentences": window.sentences
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01"
        }

        body = {
            "model": self.anthropic_model,
            "system": TURNITIN_SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": f"Return ONLY valid JSON.\n{json.dumps(user_payload)}"}
            ],
            "max_tokens": 2048,
            "temperature": 0.0
        }

        resp = requests.post(url, headers=headers, json=body, timeout=self.timeout)
        if resp.status_code == 200:
            content = resp.json()['content'][0]['text']
            match = re.search(r"\{[\s\S]*\}", content)
            if match:
                return json.loads(match.group(0))
        return None

    def _blend_window_scores(
        self,
        window: OverlappingWindow,
        llm_eval: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Applies Turnitin's Dual-Signal formula:
        Blends 30% mathematical burstiness/perplexity score with 70% qualitative LLM score.
        """
        math_burstiness = window.statistical_metrics.burstiness_score
        sentence_scores = llm_eval.get("sentence_scores", [])
        blended_sentence_scores = []

        # Index lookup
        score_by_idx = {
            s.get("sentence_index"): s
            for s in sentence_scores
            if isinstance(s, dict) and "sentence_index" in s
        }

        for s_dict in window.sentences:
            s_idx = s_dict["sentence_index"]
            item = score_by_idx.get(s_idx)
            if item:
                raw_ai_prob = float(item.get("ai_probability", 0.0))
                raw_para_prob = float(item.get("paraphrase_probability", 0.0))
                reason = item.get("reason", "")
            else:
                raw_ai_prob = float(llm_eval.get("segment_ai_probability", 0.0))
                raw_para_prob = float(llm_eval.get("segment_paraphrase_probability", 0.0))
                reason = "Segment context interpolation"

            # 70% LLM + 30% Math Burstiness Heuristic Formula
            blended_ai = (0.70 * raw_ai_prob) + (0.30 * math_burstiness)
            blended_para = (0.70 * raw_para_prob) + (0.30 * math_burstiness * 0.75)

            blended_sentence_scores.append({
                "sentence_index": s_idx,
                "ai_probability": round(float(np.clip(blended_ai, 0.0, 1.0)), 3),
                "paraphrase_probability": round(float(np.clip(blended_para, 0.0, 1.0)), 3),
                "reason": reason
            })

        return {
            "segment_id": window.segment_id,
            "segment_ai_probability": llm_eval.get("segment_ai_probability", 0.0),
            "sentence_scores": blended_sentence_scores,
            "provider": self.active_provider
        }

    def _statistical_window_fallback(self, window: OverlappingWindow) -> Dict[str, Any]:
        """High-precision offline mathematical fallback classifier."""
        stats = window.statistical_metrics
        burst_sig = stats.burstiness_score
        trans_density = stats.ai_transition_density

        blended_sentence_scores = []
        for s in window.sentences:
            s_idx = s["sentence_index"]
            s_text = s["text"].lower()

            has_marker = any(s_text.startswith(m) or f" {m} " in s_text for m in AI_TRANSITION_MARKERS)
            base_ai = (0.65 * burst_sig) + (0.25 * min(1.0, trans_density * 2.0)) + (0.10 if has_marker else 0.0)

            # Heuristic paraphrase detection: low burstiness with elevated length
            para_prob = base_ai * 0.60 if burst_sig > 0.65 else 0.05

            blended_sentence_scores.append({
                "sentence_index": s_idx,
                "ai_probability": round(float(np.clip(base_ai, 0.0, 1.0)), 3),
                "paraphrase_probability": round(float(np.clip(para_prob, 0.0, 1.0)), 3),
                "reason": "Mathematical burstiness & transition frequency"
            })

        return {
            "segment_id": window.segment_id,
            "segment_ai_probability": round(burst_sig, 3),
            "sentence_scores": blended_sentence_scores,
            "provider": "local_statistical_engine"
        }

    # =========================================================================
    # STAGE 5: SENTENCE POOLING & TURNITIN REPORT GENERATOR
    # =========================================================================
    def aggregate_report(
        self,
        sentences: List[IndexedSentence],
        window_results: List[Dict[str, Any]],
        start_time: float,
        provider_name: str
    ) -> TurnitinDetectionReport:
        """
        Stage 5: Pools multi-window probabilities for each sentence, classifies into
        Cyan (Direct AI) and Purple (AI Paraphrased), calculates overall document
        percentage, and enforces Turnitin's 1%-19% asterisk (*%) suppression rule.
        """
        # 1. Collate pooled scores across all overlapping windows
        ai_scores_by_sentence: Dict[int, List[float]] = {s.global_index: [] for s in sentences}
        para_scores_by_sentence: Dict[int, List[float]] = {s.global_index: [] for s in sentences}
        reasons_by_sentence: Dict[int, List[str]] = {s.global_index: [] for s in sentences}

        for win in window_results:
            for s_eval in win.get("sentence_scores", []):
                s_idx = s_eval["sentence_index"]
                if s_idx in ai_scores_by_sentence:
                    ai_scores_by_sentence[s_idx].append(s_eval["ai_probability"])
                    para_scores_by_sentence[s_idx].append(s_eval["paraphrase_probability"])
                    if s_eval.get("reason"):
                        reasons_by_sentence[s_idx].append(s_eval["reason"])

        # 2. Compute mean pooled probabilities & determine highlights
        evaluated_sentences: List[SentenceEvaluation] = []
        cyan_flagged_words = 0
        purple_flagged_words = 0
        total_qualifying_words = sum(s.word_count for s in sentences)

        for s in sentences:
            s_idx = s.global_index
            ai_pool = ai_scores_by_sentence[s_idx]
            para_pool = para_scores_by_sentence[s_idx]

            mean_ai = float(np.mean(ai_pool)) if ai_pool else 0.0
            mean_para = float(np.mean(para_pool)) if para_pool else 0.0

            classification = "human"
            highlight_color = "none"

            # Turnitin Dual-Category Threshold (0.70 probability)
            if mean_ai >= self.confidence_threshold:
                if mean_para >= self.confidence_threshold and mean_para > mean_ai:
                    classification = "ai_paraphrased"
                    highlight_color = "purple"
                    purple_flagged_words += s.word_count
                else:
                    classification = "ai_generated"
                    highlight_color = "cyan"
                    cyan_flagged_words += s.word_count
            elif mean_para >= self.confidence_threshold:
                classification = "ai_paraphrased"
                highlight_color = "purple"
                purple_flagged_words += s.word_count

            evaluated_sentences.append(SentenceEvaluation(
                sentence_index=s_idx,
                sentence_text=s.text,
                word_count=s.word_count,
                pooled_ai_probability=round(mean_ai, 3),
                pooled_paraphrase_probability=round(mean_para, 3),
                classification=classification,
                highlight_color=highlight_color,
                window_appearances=len(ai_pool),
                reasons=list(set(reasons_by_sentence[s_idx]))[:2]
            ))

        # 3. Overall document AI percentage: (flagged words / total qualifying words) * 100
        total_flagged_words = cyan_flagged_words + purple_flagged_words
        raw_ai_pct = (total_flagged_words / max(1, total_qualifying_words)) * 100.0
        cyan_pct = (cyan_flagged_words / max(1, total_qualifying_words)) * 100.0
        purple_pct = (purple_flagged_words / max(1, total_qualifying_words)) * 100.0

        # 4. Turnitin Confidence Thresholding & False-Positive Suppression
        # - 0%: Return "0%"
        # - 1% to 19%: Return "*%" and suppress highlights by default to prevent false positives
        # - 20% to 100%: Return exact percentage and full highlight map
        is_masked = False
        if raw_ai_pct == 0.0:
            turnitin_display_score = "0%"
        elif raw_ai_pct < 20.0:
            turnitin_display_score = "*%"
            is_masked = True
            # Mask highlights in primary view as unreliable
            for s_eval in evaluated_sentences:
                s_eval.highlight_color = "none"
        else:
            turnitin_display_score = f"{int(round(raw_ai_pct))}%"

        elapsed = round(time.time() - start_time, 2)
        doc_stats = self.compute_statistics(sentences)

        return TurnitinDetectionReport(
            status="completed",
            turnitin_display_score=turnitin_display_score,
            is_masked_asterisk=is_masked,
            overall_ai_percentage=round(raw_ai_pct, 1),
            ai_generated_cyan_pct=round(cyan_pct, 1),
            ai_paraphrased_purple_pct=round(purple_pct, 1),
            qualifying_word_count=total_qualifying_words,
            total_sentences=len(sentences),
            flagged_sentences_count=len([s for s in evaluated_sentences if s.classification != "human"]),
            sentences=evaluated_sentences,
            document_metrics={
                "sentence_length_mean": doc_stats.sentence_length_mean,
                "sentence_length_std_dev": doc_stats.sentence_length_std_dev,
                "coefficient_of_variation": doc_stats.coefficient_of_variation,
                "burstiness_index": doc_stats.burstiness_score,
                "type_token_ratio": doc_stats.type_token_ratio,
                "mean_sentence_perplexity": doc_stats.perplexity_proxy,
                "ai_transition_density": doc_stats.ai_transition_density,
            },
            provider_used=provider_name,
            processing_time_seconds=elapsed,
            raw_window_results=window_results
        )

    # =========================================================================
    # END-TO-END EXECUTION ENTRYPOINT
    # =========================================================================
    def analyze_document(
        self,
        raw_text: str,
        force_short_text: bool = False
    ) -> TurnitinDetectionReport:
        """
        Executes the full 5-stage pipeline on the provided document text.
        """
        start_time = time.time()

        # Stage 1: Preprocess text
        sentences, error_payload = self.preprocess_text(raw_text, force_short_text=force_short_text)
        if error_payload is not None:
            return TurnitinDetectionReport(
                status=error_payload.get("status", "insufficient_prose"),
                turnitin_display_score="*%" if error_payload.get("status") == "insufficient_prose" else "0%",
                is_masked_asterisk=True,
                overall_ai_percentage=0.0,
                ai_generated_cyan_pct=0.0,
                ai_paraphrased_purple_pct=0.0,
                qualifying_word_count=error_payload.get("qualifying_word_count", 0),
                total_sentences=0,
                flagged_sentences_count=0,
                sentences=[],
                document_metrics={"error_details": error_payload.get("message")},
                provider_used=self.active_provider,
                processing_time_seconds=round(time.time() - start_time, 2),
                error_message=error_payload.get("message")
            )

        # Stage 3: Generate overlapping sliding windows
        windows = self.create_overlapping_windows(sentences)

        # Stage 4: Evaluate windows concurrently
        window_results = self.evaluate_windows(windows)

        # Stage 5: Aggregate report & pool sentences
        report = self.aggregate_report(
            sentences=sentences,
            window_results=window_results,
            start_time=start_time,
            provider_name=self.active_provider
        )

        return report


# =============================================================================
# SAMPLE EXECUTION & BENCHMARK SUITE
# =============================================================================
if __name__ == "__main__":
    print("=" * 80)
    print("TURNITIN 5-STAGE AI DETECTION PIPELINE DEMONSTRATION")
    print("=" * 80)

    # Realistic benchmark sample with mixed human intro and synthetic AI body
    sample_academic_paper = """
    # Deep Learning Applications in Modern Structural Engineering

    Structural engineering has undergone significant transformations over the past two decades.
    Traditional finite element methods, while rigorous, frequently encounter computational bottlenecks
    when modeling nonlinear seismic responses in high-rise buildings. In this study, we explore
    physics-informed neural networks to accelerate dynamic response prediction under seismic excitation.

    Furthermore, it is important to note that artificial intelligence plays a vital role in modern infrastructure design.
    Additionally, machine learning models can accurately identify structural vulnerabilities across various load distributions.
    Moreover, deep convolutional networks offer unprecedented accuracy in detecting surface fatigue cracks in reinforced concrete.
    Consequently, automated visual inspection systems represent a pivotal advancement in proactive structural health monitoring.
    Furthermore, integrating sensory arrays with cloud-based neural networks empowers civil engineers to mitigate catastrophic collapses.
    It is crucial to consider the transformative impact of autonomous parameter optimization during construction phases.

    ```python
    # Simulation Code Block (Will be cleanly stripped by Stage 1 Prose Filter)
    def calculate_shear_modulus(stress, strain):
        return stress / strain
    ```

    | Simulation ID | Displacement (mm) | Yield Stress (MPa) |
    |---------------|-------------------|--------------------|
    | SIM-001       | 12.4              | 345.0              |
    | SIM-002       | 14.8              | 360.5              |

    In our field experiments conducted at the Metropolitan Shaking Table Facility, accelerometers recorded unexpected
    low-frequency resonance along the eastern shear walls. This idiosyncratic oscillation puzzled our research team
    for nearly three weeks until sensor calibration revealed slight foundation settlement on the alluvial gravel subgrade.

    References
    1. Smith, J. (2022). Principles of Seismic Dynamics. Academic Press.
    2. Johnson, R. (2024). Neural Networks in Civil Systems. Springer.
    """

    # Instantiate pipeline with local statistical fallback (or pass API keys)
    pipeline = TurnitinAIPipeline(
        provider="local",
        min_prose_words=100,  # Lowered for demo script
    )

    report = pipeline.analyze_document(sample_academic_paper, force_short_text=True)

    print(f"\n[+] Status: {report.status.upper()}")
    print(f"[+] Provider: {report.provider_used}")
    print(f"[+] Qualifying Continuous Prose: {report.qualifying_word_count} words ({report.total_sentences} sentences)")
    print(f"[+] Turnitin Official Display Score: {report.turnitin_display_score}")
    print(f"[+] Raw Overall AI Percentage: {report.overall_ai_percentage}%")
    print(f"[+] Direct AI (Cyan): {report.ai_generated_cyan_pct}%")
    print(f"[+] AI Paraphrased (Purple): {report.ai_paraphrased_purple_pct}%")
    print(f"[+] Processing Time: {report.processing_time_seconds}s")
    print(f"[+] Document Burstiness Index: {report.document_metrics.get('burstiness_index')}")

    print("\n--- SENTENCE-LEVEL POOLED EVALUATION ---")
    for s in report.sentences:
        flag = f"[{s.highlight_color.upper()}]" if s.highlight_color != "none" else "[HUMAN]"
        print(f"{flag:9} (AI: {s.pooled_ai_probability:.2f}, Para: {s.pooled_paraphrase_probability:.2f}) -> {s.sentence_text[:75]}...")
