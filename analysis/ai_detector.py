"""
Turnitin-Style Calibrated AI Writing Detection Engine.
Modular, explainable architecture implementing:
1. Academic text preprocessing & language validation
2. Multi-dimensional statistical and linguistic feature extraction (MTLD, Burstiness, Perplexity)
3. Calibrated supervised classifier + rule-based baseline
4. Mixed-authorship sliding window & segment evaluation
5. False-positive suppression protocol (<20% thresholding)
"""
import time
import logging
from typing import Optional, Dict, Any

from .preprocessor import DocumentPreprocessor
from .features import FeatureExtractor
from .classifier import CalibratedAIClassifier, RuleBasedBaselineDetector
from .segments import SegmentAnalyzer

logger = logging.getLogger(__name__)


class AIDetectionEngine:
    """
    Modular AI writing detection engine orchestrating preprocessing,
    feature extraction, multi-model classification, and segment aggregation.
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

            # 2. Preprocessing & Abbreviation-Aware Segmentation
            paragraphs, sentences, stats = self.preprocessor.process(raw_full_text)

            if not sentences:
                ai_report.status = AIReport.Status.COMPLETED
                ai_report.overall_ai_score = 0.0
                ai_report.processing_time_seconds = round(time.time() - start_time, 2)
                ai_report.save()
                return ai_report

            # 3. Feature Extraction (Burstiness, MTLD, Entropy, PPL Proxy, Markers)
            doc_features = self.feature_extractor.extract_document_features(sentences, raw_full_text)

            # 4. Multi-Scale Window & Segment Analysis
            evaluated_sentences, segments, summary = self.segment_analyzer.analyze_document_segments(
                paragraphs=paragraphs,
                all_sentences=sentences,
                doc_features=doc_features,
            )

            # 5. Populate and Persist AIReport
            ai_report.overall_ai_score = summary['overall_ai_score']
            ai_report.ai_sentence_count = summary['ai_sentence_count']
            ai_report.human_sentence_count = summary['human_sentence_count']
            ai_report.total_sentences = summary['total_sentences']
            ai_report.perplexity_score = doc_features['perplexity_score']
            ai_report.burstiness_score = doc_features['burstiness']
            ai_report.sentences_data = evaluated_sentences
            ai_report.segments_data = segments
            ai_report.model_version = summary['model_version']
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
