"""
Mixed-Authorship & Multi-Scale Segment Analysis Engine.
Analyzes academic prose across overlapping windows and paragraphs to detect:
1. Pure AI-generated text
2. Pure Human-written text
3. Mixed / human-edited AI text
4. Uncertain or unclassified text
"""
from typing import List, Dict, Any, Tuple


class SegmentAnalyzer:
    """
    Performs multi-scale sliding window and paragraph-level mixed-authorship detection.
    """

    def __init__(self, classifier=None, rule_baseline=None, feature_extractor=None):
        if classifier is None:
            from .classifier import CalibratedAIClassifier
            self.classifier = CalibratedAIClassifier()
        else:
            self.classifier = classifier

        if rule_baseline is None:
            from .classifier import RuleBasedBaselineDetector
            self.rule_baseline = RuleBasedBaselineDetector()
        else:
            self.rule_baseline = rule_baseline

        if feature_extractor is None:
            from .features import FeatureExtractor
            self.extractor = FeatureExtractor()
        else:
            self.extractor = feature_extractor

    def analyze_document_segments(
        self,
        paragraphs: List[Any],
        all_sentences: List[Any],
        doc_features: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """
        Executes dual-resolution evaluation:
        1. Sentence-level analysis with offsets and specific signals
        2. Multi-sentence segment / window analysis for mixed-authorship detection
        3. Document-level calibrated aggregation with false-positive suppression
        """
        evaluated_sentences = []
        total_words = 0
        total_ai_words = 0
        total_uncertain_words = 0
        ai_sentence_count = 0
        human_sentence_count = 0
        uncertain_sentence_count = 0

        # Step 1: Detailed Sentence-Level Scoring
        for s in all_sentences:
            s_text = getattr(s, 'clean_text', str(s))
            w_count = getattr(s, 'word_count', len(s_text.split()))
            total_words += w_count

            # Classification & calibration
            ml_prob, ml_conf, is_ood = self.classifier.predict_sentence_probability(s_text)
            rule_score, rule_signals = self.rule_baseline.evaluate(s_text, doc_features)

            # Synthesize ensemble score: 65% Calibrated ML + 35% Heuristic Rule Prior
            composite_score = (ml_prob * 0.65) + (rule_score * 0.35)

            # Academic False-Positive Protection for borderline cases:
            has_markers = bool(rule_signals)
            if not has_markers and doc_features.get('marker_density', 0.0) < 0.10 and ml_prob < 0.65:
                composite_score = min(composite_score, 0.45)

            composite_score = min(0.99, max(0.01, composite_score))

            # Uncertainty check: Out of distribution, short fragments, or borderline scores
            is_uncertain = is_ood or (0.42 <= composite_score <= 0.55 and ml_conf < 0.35)
            is_ai = (composite_score >= 0.55) and not is_uncertain
            is_human = (composite_score < 0.42) and not is_uncertain

            if is_uncertain:
                status = "Uncertain"
                uncertain_sentence_count += 1
                total_uncertain_words += w_count
            elif is_ai:
                status = "AI-associated"
                ai_sentence_count += 1
                total_ai_words += w_count
            else:
                status = "Human-written"
                human_sentence_count += 1

            signals = list(rule_signals)
            if ml_prob >= 0.70:
                signals.append(f"Calibrated ML confidence: {ml_prob:.0%}")
            if is_ood:
                signals.append("Out-of-Distribution or irregular format")

            evaluated_sentences.append({
                'index': getattr(s, 'index', len(evaluated_sentences) + 1),
                'sentence': s_text,
                'start_char': getattr(s, 'start_char', 0),
                'end_char': getattr(s, 'end_char', len(s_text)),
                'paragraph_index': getattr(s, 'paragraph_index', 1),
                'word_count': w_count,
                'ai_score': round(composite_score * 100, 1),
                'confidence': round(ml_conf, 2),
                'is_ai': is_ai,
                'status': status,
                'signals': signals[:4],
            })

        # Step 2: Multi-Sentence Sliding Window / Segment Analysis (Window size: 3 sentences)
        segments = []
        window_size = 3
        num_sentences = len(evaluated_sentences)

        for i in range(0, max(1, num_sentences), max(1, window_size - 1)):
            chunk = evaluated_sentences[i:i + window_size]
            if not chunk:
                continue

            seg_id = f"seg-{len(segments) + 1}"
            seg_start = chunk[0]['start_char']
            seg_end = chunk[-1]['end_char']
            seg_words = sum(s['word_count'] for s in chunk)

            # Calculate window-level metrics
            avg_ai_score = sum(s['ai_score'] * s['word_count'] for s in chunk) / max(seg_words, 1)
            avg_conf = sum(s['confidence'] for s in chunk) / len(chunk)

            has_ai = any(s['is_ai'] for s in chunk)
            has_human = any(s['status'] == "Human-written" for s in chunk)
            has_uncertain = any(s['status'] == "Uncertain" for s in chunk)

            if has_uncertain and not (has_ai or has_human):
                seg_status = "Uncertain"
            elif has_ai and has_human:
                seg_status = "Mixed"
            elif has_ai:
                seg_status = "AI-associated"
            else:
                seg_status = "Human-written"

            # Aggregate window signals
            seg_signals = []
            for s in chunk:
                for sig in s['signals']:
                    if sig not in seg_signals:
                        seg_signals.append(sig)

            segments.append({
                'segment_id': seg_id,
                'start_char': seg_start,
                'end_char': seg_end,
                'sentence_indices': [s['index'] for s in chunk],
                'word_count': seg_words,
                'ai_score': round(avg_ai_score, 1),
                'confidence': round(avg_conf, 2),
                'status': seg_status,
                'detection_signals': seg_signals[:5],
            })

        # Step 3: Calibrated Document-Level Aggregation
        raw_pct = (total_ai_words / max(total_words, 1)) * 100
        uncertain_pct = (total_uncertain_words / max(total_words, 1)) * 100

        # Preserve authentic percentage and sentences without artificial zeroing
        is_below_threshold = raw_pct < 20.0
        final_score = round(raw_pct, 1)

        summary = {
            'overall_ai_score': final_score,
            'raw_uncalibrated_pct': round(raw_pct, 1),
            'is_below_threshold': is_below_threshold,
            'total_sentences': num_sentences,
            'ai_sentence_count': ai_sentence_count,
            'human_sentence_count': human_sentence_count,
            'uncertain_sentence_count': uncertain_sentence_count,
            'uncertain_percentage': round(uncertain_pct, 1),
            'model_confidence': round(sum(s['confidence'] for s in evaluated_sentences) / max(num_sentences, 1), 2),
            'model_version': 'TurnitinStyle-AI-V2.5-Calibrated',
            'limitations': (
                "AI writing detection is probabilistic and reflects statistical text characteristics. "
                "Scores below the 20% threshold should be interpreted with caution. "
                "Detection results must not be used as the sole determinant for academic misconduct decisions."
            ),
        }

        return evaluated_sentences, segments, summary
