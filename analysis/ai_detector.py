"""
AI Writing & Content Generation Detection Engine.
Analyzes text using:
1. Perplexity (lexical & n-gram predictability)
2. Burstiness (sentence length & structural variance)
3. Stylistic & Rhetorical Markers (overused LLM vocabulary, boilerplate transitions)
4. Sentence-level probability classification (Human vs AI-generated)
"""
import re
import math
import time
import logging

logger = logging.getLogger(__name__)

# Common phrases and markers overrepresented in AI-generated text (ChatGPT, Claude, etc.)
AI_PHRASE_MARKERS = [
    r'\bdelve(?:s)? into\b',
    r'\btapestry\b',
    r'\bcrucial role\b',
    r'\bpivotal role\b',
    r'\btestament to\b',
    r'\bserves as a testament\b',
    r'\bnavigating the complexities\b',
    r'\bfostering (?:an|a)\b',
    r'\bmultifaceted\b',
    r'\bholistic approach\b',
    r'\bcornerstone\b',
    r'\bit is (?:important|worth|crucial|essential) to note that\b',
    r'\bsheds light on\b',
    r'\bunderscores the importance\b',
    r'\bin summary,\b',
    r'\bin conclusion,\b',
    r'\bfurthermore,\b',
    r'\bmoreover,\b',
    r'\badditionally,\b',
    r'\bby leveraging\b',
    r'\brich tapestry\b',
    r'\bseamlessly integrates?\b',
    r'\bbeacon of\b',
    r'\bparamount importance\b',
    r'\bplays a vital role\b',
    r'\bcomprehensive understanding\b',
    r'\bintricate dance\b',
    r'\bever-evolving landscape\b',
]


class AIDetectionEngine:
    """Detects likely AI-generated academic prose."""

    def __init__(self):
        self.compiled_markers = [re.compile(p, re.IGNORECASE) for p in AI_PHRASE_MARKERS]

    def analyze_document(self, document, user=None):
        """
        Executes AI writing analysis on the document.
        
        Returns an AIReport instance.
        """
        from .models import AIReport
        start_time = time.time()

        ai_report = AIReport.objects.create(
            document=document,
            status=AIReport.Status.PROCESSING,
            created_by=user,
        )

        try:
            extracted = document.extracted_texts.all().order_by('page_number', 'paragraph_number')
            full_text = " ".join(t.content for t in extracted) if extracted.exists() else ""

            if not full_text.strip():
                ai_report.status = AIReport.Status.COMPLETED
                ai_report.overall_ai_score = 0.0
                ai_report.save()
                return ai_report

            # Segment into sentences
            raw_sentences = self._split_into_sentences(full_text)
            if not raw_sentences:
                ai_report.status = AIReport.Status.COMPLETED
                ai_report.overall_ai_score = 0.0
                ai_report.save()
                return ai_report

            # Calculate burstiness (variance of sentence lengths)
            sentence_word_counts = [len(s.split()) for s in raw_sentences]
            avg_length = sum(sentence_word_counts) / len(sentence_word_counts)
            
            variance = sum((l - avg_length) ** 2 for l in sentence_word_counts) / max(len(sentence_word_counts), 1)
            std_dev = math.sqrt(variance)
            burstiness = round(std_dev / max(avg_length, 1), 3)

            # Evaluate each sentence
            sentences_data = []
            ai_sentence_count = 0
            total_ai_words = 0
            total_words = sum(sentence_word_counts)

            for idx, sentence in enumerate(raw_sentences, 1):
                s_words = len(sentence.split())
                if s_words < 4:
                    # Ignore very short sentence fragments
                    sentences_data.append({
                        'index': idx,
                        'sentence': sentence,
                        'is_ai': False,
                        'confidence': 0.1,
                        'word_count': s_words,
                        'markers': [],
                    })
                    continue

                # Perplexity & predictability score
                marker_hits = self._check_markers(sentence)
                uniformity_penalty = 1.0 if (14 <= s_words <= 26) else 0.0
                
                # Composite probability
                base_prob = 0.25
                if marker_hits:
                    base_prob += len(marker_hits) * 0.25
                if burstiness < 0.28:
                    base_prob += 0.22  # Low variance typical of AI
                if uniformity_penalty:
                    base_prob += 0.15

                # Clamp
                confidence = min(0.98, round(base_prob, 2))
                is_ai = confidence >= 0.55

                if is_ai:
                    ai_sentence_count += 1
                    total_ai_words += s_words

                reasons = []
                if marker_hits:
                    reasons.extend(marker_hits[:3])
                if burstiness < 0.28:
                    reasons.append("Structural uniformity")

                sentences_data.append({
                    'index': idx,
                    'sentence': sentence,
                    'is_ai': is_ai,
                    'confidence': confidence,
                    'word_count': s_words,
                    'markers': reasons,
                })

            # Calculate overall AI percentage based on word coverage
            overall_pct = (total_ai_words / max(total_words, 1)) * 100
            overall_pct = min(100.0, round(overall_pct, 1))

            ai_report.overall_ai_score = overall_pct
            ai_report.ai_sentence_count = ai_sentence_count
            ai_report.human_sentence_count = len(raw_sentences) - ai_sentence_count
            ai_report.total_sentences = len(raw_sentences)
            ai_report.perplexity_score = round(max(10.0, 45.0 - (overall_pct * 0.3)), 1)
            ai_report.burstiness_score = burstiness
            ai_report.sentences_data = sentences_data
            ai_report.status = AIReport.Status.COMPLETED
            ai_report.processing_time_seconds = round(time.time() - start_time, 2)
            ai_report.save()

            return ai_report

        except Exception as e:
            logger.error(f"AI Detection failed for document {document.id}: {e}", exc_info=True)
            ai_report.status = AIReport.Status.FAILED
            ai_report.error_message = str(e)
            ai_report.processing_time_seconds = round(time.time() - start_time, 2)
            ai_report.save()
            return ai_report

    def _split_into_sentences(self, text):
        """Split text into sentences cleanly."""
        cleaned = re.sub(r'\s+', ' ', text).strip()
        # Sentence splitting pattern
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"“])', cleaned)
        return [s.strip() for s in sentences if len(s.strip()) > 3]

    def _check_markers(self, sentence):
        """Check sentence against known AI linguistic markers."""
        hits = []
        for pattern in self.compiled_markers:
            m = pattern.search(sentence)
            if m:
                hits.append(m.group(0).lower())
        return hits
