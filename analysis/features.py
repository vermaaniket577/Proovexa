"""
Multi-Dimensional Linguistic & Statistical Feature Extractor for AI Writing Analysis.
Extracts:
1. Perplexity & N-Gram Predictability (PPL proxy based on character & word entropy)
2. Burstiness & Structural Variance (Coefficient of variation of sentence lengths)
3. Lexical Diversity (MTLD: Measure of Textual Lexical Diversity & TTR)
4. LLM Formulaic Marker Density & Discourse Patterns
5. Repetitive Transitions & Syntactic Uniformity
"""
import re
import math
from collections import Counter
from typing import List, Dict, Any, Tuple


# Curated academic LLM marker patterns (ChatGPT, Claude, Gemini, Llama)
LLM_DISCOURSE_MARKERS = [
    # Metaphorical & grandiloquent tropes
    r'\b(?:rich\s+)?tapestry\b',
    r'\bdelve(?:s|d)?\s+into\b',
    r'\btestament\s+to\b',
    r'\bserves\s+as\s+a\s+testament\b',
    r'\bbeacon\s+of\b',
    r'\bintricate\s+(?:dance|web|dynamics)\b',
    r'\bever-evolving\s+landscape\b',
    r'\bmultifaceted\s+(?:nature|approach|aspect)\b',
    r'\bholistic\s+(?:approach|perspective|framework)\b',
    r'\bcornerstone\s+of\b',
    r'\bseamlessly\s+integrates?\b',
    
    # Overused hedging & signposts
    r'\bit\s+is\s+(?:important|crucial|essential|worth\s+noting|imperative)\s+to\s+(?:note|understand|highlight)\s+that\b',
    r'\bsheds?\s+light\s+on\b',
    r'\bunderscores?\s+the\s+(?:importance|significance|need)\b',
    r'\bplays?\s+a\s+(?:pivotal|vital|crucial|key|fundamental)\s+role\b',
    r'\bparamount\s+importance\b',
    r'\bnavigating\s+the\s+complexities\b',
    r'\bfostering\s+(?:an?|collaboration|growth|innovation)\b',
    r'\bcomprehensive\s+understanding\b',
    r'\bby\s+leveraging\b',
    
    # Predictable repetitive sentence-initial transitions
    r'^(?:furthermore|moreover|additionally|in\s+conclusion|in\s+summary|consequently|ultimately|notably),',
]


class FeatureExtractor:
    """
    Computes transparent, reproducible linguistic and statistical features
    from preprocessed academic sentences.
    """

    def __init__(self):
        self.compiled_markers = [re.compile(p, re.IGNORECASE) for p in LLM_DISCOURSE_MARKERS]
        # Common English 2-gram / 3-gram background statistics for predictability scoring
        self.common_transitions = {
            'in order to', 'as a result', 'on the other hand', 'at the same time',
            'in terms of', 'with respect to', 'due to the', 'it is clear that',
            'can be seen', 'in the context of', 'based on the', 'a wide range of',
        }

    def extract_document_features(self, sentences: List[Any], full_text: str) -> Dict[str, Any]:
        """
        Extract document-wide feature vector and statistical metrics.
        """
        if not sentences or not full_text.strip():
            return self._empty_document_features()

        word_counts = [s.word_count for s in sentences if s.word_count > 0]
        if not word_counts:
            return self._empty_document_features()

        # 1. Burstiness & Length Variance
        total_sentences = len(word_counts)
        mean_len = sum(word_counts) / total_sentences
        variance = sum((l - mean_len) ** 2 for l in word_counts) / max(total_sentences, 1)
        std_dev = math.sqrt(variance)
        burstiness = round(std_dev / max(mean_len, 1e-5), 4)

        # Sentence length distribution
        median_len = sorted(word_counts)[total_sentences // 2]
        min_len = min(word_counts)
        max_len = max(word_counts)

        # Uniformity: Fraction of sentences clustering in typical LLM bell curve (14-26 words)
        mid_range_count = sum(1 for l in word_counts if 14 <= l <= 26)
        length_uniformity_ratio = round(mid_range_count / total_sentences, 4)

        # 2. Lexical Diversity: MTLD and TTR
        all_tokens = [w.lower() for w in re.findall(r'\b[a-zA-Z]+\b', full_text)]
        total_tokens = len(all_tokens)
        ttr = round(len(set(all_tokens)) / max(total_tokens, 1), 4)
        mtld = self._calculate_mtld(all_tokens)

        # 3. N-gram Repetition & Predictability
        bigram_entropy, trigram_repetition = self._calculate_ngram_entropy(all_tokens)
        perplexity_proxy = self._estimate_perplexity(all_tokens, mean_len, burstiness)

        # 4. LLM Discourse Marker Analysis
        marker_hits_total = 0
        sentences_with_markers = 0
        marker_details = Counter()

        for s in sentences:
            s_text = getattr(s, 'clean_text', str(s))
            hits = self._find_markers(s_text)
            if hits:
                marker_hits_total += len(hits)
                sentences_with_markers += 1
                marker_details.update(hits)

        marker_density = round(marker_hits_total / max(total_sentences, 1), 4)
        marker_sentence_ratio = round(sentences_with_markers / max(total_sentences, 1), 4)

        # 5. Consecutive Transition Redundancy
        transition_repetition = self._check_transition_repetition(sentences)

        return {
            'total_sentences': total_sentences,
            'total_tokens': total_tokens,
            'mean_sentence_length': round(mean_len, 2),
            'median_sentence_length': median_len,
            'min_sentence_length': min_len,
            'max_sentence_length': max_len,
            'std_dev_sentence_length': round(std_dev, 2),
            'burstiness': burstiness,
            'length_uniformity_ratio': length_uniformity_ratio,
            'ttr': ttr,
            'mtld': round(mtld, 2),
            'bigram_entropy': round(bigram_entropy, 3),
            'trigram_repetition_rate': round(trigram_repetition, 4),
            'perplexity_score': round(perplexity_proxy, 1),
            'marker_density': marker_density,
            'marker_sentence_ratio': marker_sentence_ratio,
            'transition_repetition_rate': round(transition_repetition, 4),
            'top_markers': marker_details.most_common(5),
        }

    def extract_sentence_features(self, sentence_text: str, doc_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract features for an individual sentence relative to document context.
        """
        clean = re.sub(r'\s+', ' ', sentence_text).strip()
        tokens = [w.lower() for w in re.findall(r'\b[a-zA-Z]+\b', clean)]
        word_count = len(tokens)

        if word_count < 4:
            return {
                'word_count': word_count,
                'is_too_short': True,
                'marker_hits': [],
                'uniformity_score': 0.0,
                'lexical_density': 0.0,
                'transition_score': 0.0,
                'raw_ai_signal': 0.05,
            }

        # Marker hits
        marker_hits = self._find_markers(clean)

        # Sentence length bell-curve penalty (AI heavily overrepresents 14-25 word sentences)
        uniformity_score = 1.0 if (14 <= word_count <= 26) else (0.5 if (10 <= word_count <= 32) else 0.0)

        # Lexical uniqueness within sentence
        unique_tokens = len(set(tokens))
        internal_ttr = unique_tokens / max(word_count, 1)

        # Formulaic transition start
        has_formulaic_start = bool(re.match(
            r'^(?:furthermore|moreover|additionally|in conclusion|in summary|consequently|notably|importantly),',
            clean, re.IGNORECASE
        ))

        # Sentence-level AI probability heuristic prior
        prior = 0.20
        if marker_hits:
            prior += min(0.40, len(marker_hits) * 0.20)
        if has_formulaic_start:
            prior += 0.15
        if uniformity_score == 1.0 and doc_context.get('burstiness', 0.5) < 0.30:
            prior += 0.20
        if doc_context.get('marker_density', 0.0) > 0.25:
            prior += 0.10

        return {
            'word_count': word_count,
            'is_too_short': False,
            'marker_hits': marker_hits,
            'has_formulaic_start': has_formulaic_start,
            'uniformity_score': uniformity_score,
            'internal_ttr': round(internal_ttr, 3),
            'raw_ai_signal': min(0.95, round(prior, 3)),
        }

    def _find_markers(self, text: str) -> List[str]:
        hits = []
        for p in self.compiled_markers:
            m = p.search(text)
            if m:
                hits.append(m.group(0).lower().strip())
        return hits

    def _calculate_mtld(self, tokens: List[str], threshold: float = 0.72) -> float:
        """
        Computes Measure of Textual Lexical Diversity (MTLD).
        Calculates average segment length maintaining TTR >= threshold.
        """
        if len(tokens) < 10:
            return 50.0

        def mtld_pass(token_list):
            factors = 0
            types = set()
            start = 0
            for i, token in enumerate(token_list):
                types.add(token)
                current_len = i - start + 1
                ttr = len(types) / current_len
                if ttr <= threshold:
                    factors += 1
                    types = set()
                    start = i + 1

            remainder = len(token_list) - start
            if remainder > 0 and len(types) > 0:
                final_ttr = len(types) / remainder
                if final_ttr < 1.0:
                    factors += (1.0 - final_ttr) / (1.0 - threshold)

            return len(token_list) / max(factors, 1)

        forward = mtld_pass(tokens)
        backward = mtld_pass(list(reversed(tokens)))
        return round((forward + backward) / 2.0, 2)

    def _calculate_ngram_entropy(self, tokens: List[str]) -> Tuple[float, float]:
        """Calculates bigram entropy and trigram repetition rate."""
        if len(tokens) < 5:
            return 4.0, 0.0

        bigrams = [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]
        trigrams = [f"{tokens[i]}_{tokens[i+1]}_{tokens[i+2]}" for i in range(len(tokens) - 2)]

        # Entropy of bigrams
        counts = Counter(bigrams)
        total = len(bigrams)
        entropy = -sum((c / total) * math.log2(c / total) for c in counts.values())

        # Trigram repetition rate
        tri_counts = Counter(trigrams)
        repeated_trigrams = sum(c for c in tri_counts.values() if c > 1)
        trigram_repetition = repeated_trigrams / max(len(trigrams), 1)

        return entropy, trigram_repetition

    def _estimate_perplexity(self, tokens: List[str], mean_len: float, burstiness: float) -> float:
        """
        Generates calibrated perplexity proxy score.
        Academic human text typically ranges 45–95; raw AI prose centers 15–35.
        """
        if len(tokens) < 20:
            return 50.0

        # Lexical uniqueness factor
        uniqueness = len(set(tokens)) / len(tokens)
        base = 25.0 + (uniqueness * 35.0) + (burstiness * 30.0)
        return max(10.0, min(120.0, base))

    def _check_transition_repetition(self, sentences: List[Any]) -> float:
        """Measures consecutive sentence transitions that repeat identical connector words."""
        if len(sentences) < 3:
            return 0.0

        transition_words = []
        for s in sentences:
            text = getattr(s, 'clean_text', str(s)).strip()
            first_word = text.split()[0].lower().rstrip(',') if text else ''
            transition_words.append(first_word)

        repeats = 0
        for i in range(len(transition_words) - 1):
            if transition_words[i] and transition_words[i] == transition_words[i + 1]:
                repeats += 1

        return repeats / max(len(sentences) - 1, 1)

    def _empty_document_features(self) -> Dict[str, Any]:
        return {
            'total_sentences': 0,
            'total_tokens': 0,
            'mean_sentence_length': 0.0,
            'median_sentence_length': 0,
            'min_sentence_length': 0,
            'max_sentence_length': 0,
            'std_dev_sentence_length': 0.0,
            'burstiness': 0.0,
            'length_uniformity_ratio': 0.0,
            'ttr': 0.0,
            'mtld': 50.0,
            'bigram_entropy': 0.0,
            'trigram_repetition_rate': 0.0,
            'perplexity_score': 50.0,
            'marker_density': 0.0,
            'marker_sentence_ratio': 0.0,
            'transition_repetition_rate': 0.0,
            'top_markers': [],
        }
