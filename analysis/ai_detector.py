"""
Turnitin-Style Calibrated AI Writing Detection Engine.
Modular, explainable architecture implementing:
1. Academic text preprocessing & language validation
2. Multi-dimensional statistical and linguistic feature extraction (MTLD, Burstiness, Perplexity)
3. Calibrated supervised classifier + rule-based baseline
4. Mixed-authorship sliding window & segment evaluation
5. False-positive suppression protocol (<20% thresholding)
"""
import re
import time
import logging
from typing import Optional, Dict, Any

from .preprocessor import DocumentPreprocessor
from .features import FeatureExtractor
from .classifier import CalibratedAIClassifier, RuleBasedBaselineDetector
from .segments import SegmentAnalyzer

from .turnitin_ai_engine import TurnitinAIDetector
from .ai_api_client import AIAPIClient

logger = logging.getLogger(__name__)


class AIDetectionEngine:
    """
    Modular AI writing detection engine orchestrating preprocessing,
    feature extraction, multi-model classification, and segment aggregation.
    Supports live Google Gemini / OpenAI API verification with calibrated offline fallback.
    """

    def __init__(self):
        self.preprocessor = DocumentPreprocessor()
        self.feature_extractor = FeatureExtractor()
        self.classifier = CalibratedAIClassifier()
        self.rule_baseline = RuleBasedBaselineDetector(self.feature_extractor)
        self.segment_analyzer = SegmentAnalyzer(
            classifier=self.classifier,
            rule_baseline=self.rule_baseline,
            feature_extractor=self.feature_extractor,
        )
        self.turnitin_detector = TurnitinAIDetector()
        self.ai_api_client = AIAPIClient()

    def analyze_document(self, document, user=None):
        """
        Executes complete AI writing analysis pipeline on document.
        Returns saved and populated AIReport instance.
        """
        from .models import AIReport
        start_time = time.time()

        ai_report = AIReport.objects.create(
            document=document,
            status=AIReport.Status.PROCESSING,
            created_by=user,
        )

        try:
            # 1. Ingestion: Extract text from document
            extracted_qs = document.extracted_texts.all().order_by('page_number', 'paragraph_number')
            raw_full_text = " ".join(t.content for t in extracted_qs) if extracted_qs.exists() else ""

            if not raw_full_text.strip():
                ai_report.status = AIReport.Status.COMPLETED
                ai_report.overall_ai_score = 0.0
                ai_report.processing_time_seconds = round(time.time() - start_time, 2)
                ai_report.save()
                return ai_report

            # 2. Stage 1-4 Turnitin AI Detection Pipeline
            turnitin_result = self.turnitin_detector.evaluate_document(raw_full_text)

            # 3. Preprocessing & Abbreviation-Aware Segmentation
            paragraphs, sentences, stats = self.preprocessor.process(raw_full_text)

            if not sentences:
                ai_report.status = AIReport.Status.COMPLETED
                ai_report.overall_ai_score = 0.0
                ai_report.processing_time_seconds = round(time.time() - start_time, 2)
                ai_report.save()
                return ai_report

            # 4. Feature Extraction (Burstiness, MTLD, Entropy, PPL Proxy, Markers)
            doc_features = self.feature_extractor.extract_document_features(sentences, raw_full_text)

            # 5. Multi-Scale Window & Segment Analysis
            evaluated_sentences, segments, summary = self.segment_analyzer.analyze_document_segments(
                paragraphs=paragraphs,
                all_sentences=sentences,
                doc_features=doc_features,
            )

            # Merge Turnitin Dual-Category highlights (Cyan vs Purple) into evaluated sentences
            tb_lookup = {
                re.sub(r'\s+', ' ', s_item['sentence'].lower().strip()[:40]): s_item
                for s_item in turnitin_result.get('sentence_breakdown', [])
            }
            for es in evaluated_sentences:
                clean_s = re.sub(r'\s+', ' ', es.get('sentence', '').lower().strip()[:40])
                if clean_s in tb_lookup:
                    tb_match = tb_lookup[clean_s]
                    es['highlight_color'] = tb_match.get('highlight_color', 'none')
                    es['category'] = tb_match.get('category', es.get('category', 'Human'))
                    es['perplexity'] = tb_match.get('perplexity', doc_features.get('perplexity_score', 50.0))
                else:
                    if es.get('is_ai', False):
                        es['highlight_color'] = 'cyan'
                    else:
                        es['highlight_color'] = 'none'

            # 6. Optional Live AI API Cross-Validation (Google Gemini / OpenAI)
            active_provider = "TurnitinStyle-AI-V2.5-SlidingWindow"
            if self.ai_api_client.is_api_available():
                try:
                    api_eval = self.ai_api_client.detect_ai_writing(raw_full_text)
                    if api_eval and 'overall_ai_score' in api_eval:
                        # Blend external API score with calibrated sliding window
                        api_score = float(api_eval.get('overall_ai_score', 0.0))
                        raw_ai_score = round(0.5 * raw_ai_score + 0.5 * api_score, 1)
                        if 'ai_generated_pct' in api_eval:
                            turnitin_result['ai_generated_only_cyan_pct'] = round(0.5 * turnitin_result.get('ai_generated_only_cyan_pct', 0.0) + 0.5 * float(api_eval.get('ai_generated_pct', 0.0)), 1)
                        if 'ai_paraphrased_pct' in api_eval:
                            turnitin_result['ai_paraphrased_purple_pct'] = round(0.5 * turnitin_result.get('ai_paraphrased_purple_pct', 0.0) + 0.5 * float(api_eval.get('ai_paraphrased_pct', 0.0)), 1)
                        active_provider = f"TurnitinStyle-AI-V2.5 + {api_eval.get('provider', 'AI API')}"
                        if api_eval.get('summary'):
                            summary['limitations'] = f"AI API Analysis: {api_eval.get('summary')} | " + summary.get('limitations', '')
                except Exception as api_err:
                    logger.warning(f"External AI API validation skipped: {api_err}")

            # 7. Populate and Persist AIReport
            # If Turnitin dual-category pipeline ran, use its raw score and metrics
            raw_ai_score = turnitin_result.get('raw_total_ai_pct', summary['overall_ai_score'])
            ai_report.overall_ai_score = raw_ai_score
            ai_report.ai_generated_only_cyan_pct = turnitin_result.get('ai_generated_only_cyan_pct', raw_ai_score)
            ai_report.ai_paraphrased_purple_pct = turnitin_result.get('ai_paraphrased_purple_pct', 0.0)
            ai_report.qualifying_word_count = turnitin_result.get('document_metrics', {}).get('qualifying_word_count', len(raw_full_text.split()))
            ai_report.below_300_word_warning = turnitin_result.get('document_metrics', {}).get('below_300_word_minimum', False)

            ai_report.ai_sentence_count = sum(1 for s in evaluated_sentences if s.get('highlight_color') != 'none')
            ai_report.human_sentence_count = len(evaluated_sentences) - ai_report.ai_sentence_count
            ai_report.total_sentences = len(evaluated_sentences)
            ai_report.perplexity_score = turnitin_result.get('document_metrics', {}).get('mean_sentence_perplexity', doc_features['perplexity_score'])
            ai_report.burstiness_score = turnitin_result.get('document_metrics', {}).get('burstiness_index', doc_features['burstiness'])
            ai_report.sentences_data = evaluated_sentences
            ai_report.segments_data = segments
            ai_report.model_version = active_provider
            ai_report.model_confidence = summary['model_confidence']
            ai_report.uncertain_percentage = summary['uncertain_percentage']
            ai_report.linguistic_features = doc_features
            ai_report.limitations = summary['limitations']
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

    def evaluate_text_snippet(self, text: str) -> Dict[str, Any]:
        """
        Direct API inference method for raw text snippets.
        Useful for microservice calls and interactive validation.
        """
        paragraphs, sentences, stats = self.preprocessor.process(text)
        if not sentences:
            return {'overall_ai_score': 0.0, 'status': 'Empty', 'sentences': []}

        doc_features = self.feature_extractor.extract_document_features(sentences, text)
        evaluated_sentences, segments, summary = self.segment_analyzer.analyze_document_segments(
            paragraphs=paragraphs,
            all_sentences=sentences,
            doc_features=doc_features,
        )

        return {
            'overall_ai_score': summary['overall_ai_score'],
            'is_below_threshold': summary['is_below_threshold'],
            'model_confidence': summary['model_confidence'],
            'uncertain_percentage': summary['uncertain_percentage'],
            'linguistic_features': doc_features,
            'segments': segments,
            'sentences': evaluated_sentences,
            'limitations': summary['limitations'],
        }
