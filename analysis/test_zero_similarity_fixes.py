"""
Comprehensive Unit and Integration Tests for Plagiarism Detection & Reporting Fixes.

Covers all 5 Failure Points:
1. Asynchronous Polling & Race Condition Check (status transitions, exponential backoff, status endpoints).
2. Document Text Extraction Validation (assertion logging, empty / < 20 word guards, null bytes, UTF-8 / Devanagari).
3. Exclusion Filter Debugging (anchored bibliography headers, unclosed quote runaway protection).
4. Repository & Match Query Configuration (all 3 repos enabled, min_match_words <= 8, non-zero duplicate matches).
5. Top Sources Data Binding & PDF Generation (dual snake_case / camelCase binding, dynamic Turnitin overview generation).
"""
import io
import time
import uuid
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, Institution
from documents.models import Document, ExtractedText, ReferenceSource
from documents.extractors import clean_extracted_string, ExtractionResult, TXTExtractor, extract_and_validate_text
from analysis.models import SimilarityReport, MatchedPassage
from analysis.engine import AnalysisEngine
from analysis.exclusions import filter_bibliography, filter_quotes, ExclusionEngine
from analysis.turnitin_similarity_engine import TurnitinSimilarityPipeline
from analysis.services import wait_for_report_completion, get_completed_report
from reports.criteria import compute_report_criteria
from reports.pdf_generator import generate_pdf_report, generate_turnitin_overview_pdf


class ZeroSimilarityFixesTestCase(TestCase):
    """Automated verification for all 5 plagiarism reporting failure points."""

    def setUp(self):
        # Prevent external network calls during tests
        self.patcher = patch(
            'sources.providers.multi_source_search',
            return_value={'results': [], 'sources_checked': ['Local Repository'], 'failed_sources': []}
        )
        self.mock_search = self.patcher.start()

        self.institution = Institution.objects.create(
            name="Apex University Integrity Lab",
            short_name="AUIL",
            domain="apex.edu",
            is_active=True
        )

        self.user = User.objects.create_user(
            username="investigator",
            email="investigator@apex.edu",
            password="testpassword123",
            role=User.Role.TEACHER,
            institution=self.institution
        )

        self.client = Client()
        self.client.force_login(self.user)

        # Standard reference text for plagiarism matching tests
        self.reference_body = (
            "Modern deep learning architectures rely heavily on transformer self-attention mechanisms "
            "to capture long-range linguistic context and cross-modal correlations efficiently. "
            "Backpropagation through time computes partial derivatives of loss tensors with respect to hidden states, "
            "allowing multi-head attention weights to converge during large-scale self-supervised pretraining."
        )

        self.reference_source = ReferenceSource.objects.create(
            title="Transformer Attention Mechanics in Scaled Models",
            author="Vaswani et al.",
            source_type=ReferenceSource.SourceType.ACADEMIC,
            url="https://doi.org/10.48550/arXiv.1706.03762",
            doi="10.48550/arXiv.1706.03762",
            retrieved_text=self.reference_body,
            word_count=len(self.reference_body.split()),
            is_active=True
        )

    def tearDown(self):
        self.patcher.stop()

    # =========================================================================
    # Task 1: Asynchronous Polling & Race Condition Checks
    # =========================================================================

    def test_wait_for_report_completion_success(self):
        """Verify wait_for_report_completion waits and succeeds when report transitions to completed."""
        doc = Document.objects.create(
            title="Async Polling Test Doc",
            uploaded_by=self.user,
            status=Document.Status.ANALYZING
        )
        report = SimilarityReport.objects.create(
            document=doc,
            status=SimilarityReport.Status.PROCESSING,
            overall_similarity=0.0
        )

        # Simulate worker completing analysis on second check
        call_count = [0]

        def mock_refresh(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 2:
                report.status = SimilarityReport.Status.COMPLETED
                report.overall_similarity = 34.2

        with patch.object(report, 'refresh_from_db', side_effect=mock_refresh):
            is_ready = wait_for_report_completion(report, max_retries=5, initial_delay=0.01, backoff_factor=1.0)
            self.assertTrue(is_ready)
            self.assertEqual(report.status, SimilarityReport.Status.COMPLETED)
            self.assertAlmostEqual(report.overall_similarity, 34.2, places=1)

    def test_wait_for_report_completion_failure(self):
        """Verify wait_for_report_completion returns False when report marks FAILED."""
        doc = Document.objects.create(
            title="Failed Doc",
            uploaded_by=self.user,
            status=Document.Status.ANALYZING
        )
        report = SimilarityReport.objects.create(
            document=doc,
            status=SimilarityReport.Status.PROCESSING,
            overall_similarity=0.0
        )

        # Immediately transition to FAILED
        def mock_refresh():
            SimilarityReport.objects.filter(id=report.id).update(
                status=SimilarityReport.Status.FAILED,
                error_message="Worker exception during matching"
            )
            report.status = SimilarityReport.Status.FAILED

        with patch.object(report, 'refresh_from_db', side_effect=mock_refresh):
            is_ready = wait_for_report_completion(report, max_retries=3, initial_delay=0.01)
            self.assertFalse(is_ready)

    def test_analysis_status_view_processing_guards_against_zero_percent(self):
        """Verify analysis_status_view returns status=PROCESSING and similarity_ready=False while running."""
        doc = Document.objects.create(
            title="In-flight Document",
            uploaded_by=self.user,
            status=Document.Status.ANALYZING
        )
        report = SimilarityReport.objects.create(
            document=doc,
            status=SimilarityReport.Status.PROCESSING,
            overall_similarity=0.0
        )

        response = self.client.get(reverse('analysis:status', kwargs={'doc_id': doc.id}))
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['status'], 'PROCESSING')
        self.assertFalse(data['similarity_ready'])
        self.assertFalse(data['can_render_report'])
        # overall_similarity must NOT be exposed as 0% while still processing
        self.assertIsNone(data['overall_similarity'])

    def test_analysis_status_view_complete_returns_score_and_url(self):
        """Verify analysis_status_view returns COMPLETE, similarity_ready=True, and valid score when completed."""
        doc = Document.objects.create(
            title="Completed Document",
            uploaded_by=self.user,
            status=Document.Status.COMPLETED
        )
        report = SimilarityReport.objects.create(
            document=doc,
            status=SimilarityReport.Status.COMPLETED,
            overall_similarity=42.5,
            source_count=3
        )

        response = self.client.get(reverse('analysis:status', kwargs={'doc_id': doc.id}))
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['status'], 'COMPLETE')
        self.assertTrue(data['similarity_ready'])
        self.assertTrue(data['can_render_report'])
        self.assertEqual(data['overall_similarity'], 42.5)
        self.assertIn('report_url', data)
        self.assertIn('pdf_url', data)

    def test_report_status_endpoint(self):
        """Verify direct report status URL returns expected keys."""
        doc = Document.objects.create(
            title="Direct Report Status Doc",
            uploaded_by=self.user,
            status=Document.Status.COMPLETED
        )
        report = SimilarityReport.objects.create(
            document=doc,
            status=SimilarityReport.Status.COMPLETED,
            overall_similarity=19.8
        )

        response = self.client.get(reverse('reports:status', kwargs={'report_id': report.id}))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'COMPLETE')
        self.assertTrue(data['similarity_ready'])
        self.assertEqual(data['overall_similarity'], 19.8)

    # =========================================================================
    # Task 2: Document Text Extraction Validation
    # =========================================================================

    def test_clean_extracted_string_null_bytes_and_control_chars(self):
        """Verify clean_extracted_string removes null bytes and control characters while preserving valid text."""
        corrupted = "Valid text with \x00 null bytes and \x0b vertical tab and \x0c form feed."
        cleaned = clean_extracted_string(corrupted)
        self.assertNotIn("\x00", cleaned)
        self.assertNotIn("\x0b", cleaned)
        self.assertIn("Valid text with", cleaned)

    def test_clean_extracted_string_preserves_devanagari_hindi(self):
        """Verify clean_extracted_string normalizes and preserves Devanagari Hindi text."""
        hindi_text = "साहित्यिक चोरी और शोध निष्ठा का विस्तृत विश्लेषण।"
        cleaned = clean_extracted_string(hindi_text)
        self.assertEqual(cleaned, hindi_text)

    def test_extraction_validation_empty_text_raises_value_error(self):
        """Verify empty extracted text raises ValueError with clear message."""
        result = ExtractionResult(text="   \n \t  ", page_count=1)
        with self.assertRaises(ValueError) as ctx:
            result.validate(min_words=20, raise_exception=True)
        self.assertIn("Extracted document text is empty", str(ctx.exception))

    def test_extraction_validation_under_20_words_raises_value_error(self):
        """Verify short extracted text (<20 words) raises ValueError with word count."""
        result = ExtractionResult(text="This document only contains seven words total.", page_count=1)
        with self.assertRaises(ValueError) as ctx:
            result.validate(min_words=20, raise_exception=True)
        self.assertIn("Extracted only 7 words", str(ctx.exception))

    def test_extraction_validation_valid_text_succeeds(self):
        """Verify valid extracted text passes validation and returns trimmed text."""
        body = " ".join(["word"] * 25)
        result = ExtractionResult(text=f"  {body}  ", page_count=1)
        ok, validated = result.validate(min_words=20)
        self.assertTrue(ok)
        self.assertEqual(len(validated.split()), 25)

    def test_extract_and_validate_text_txt_format(self):
        """Verify extract_and_validate_text works on text content."""
        import tempfile
        content = "Modern academic research requires rigorous analysis of originality. " * 3
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as tf:
            tf.write(content)
            temp_path = tf.name

        extracted = extract_and_validate_text(temp_path, file_type='txt', min_words=10)
        self.assertGreater(len(extracted.split()), 20)

    # =========================================================================
    # Task 3: Exclusion Filter Debugging (Bibliography & Quoted Text)
    # =========================================================================

    def test_filter_bibliography_references_in_intro_is_not_truncated(self):
        """
        Verify that a mention of 'References' in early sections (first 50% of document)
        does NOT truncate or discard the following text.
        """
        intro_references = (
            "Introduction\n"
            "In reference to previous foundational literature in computer vision, "
            "we explore convolutional neural networks and attention mechanisms. "
            "Our primary contribution demonstrates that residual connections alleviate "
            "vanishing gradients across very deep architectures. "
            "Subsequent experiments confirm improved generalization across diverse benchmarks.\n\n"
            "Methodology\n"
            "We construct a multi-layer perceptual model with residual mappings. "
            "The loss function is optimized using stochastic gradient descent with momentum. "
            "Empirical results indicate a 14% relative reduction in top-1 error rate."
        )

        filtered = filter_bibliography(intro_references)
        # Whole text must remain intact; "Methodology" must not be truncated
        self.assertIn("Methodology", filtered)
        self.assertIn("Empirical results indicate", filtered)

    def test_filter_bibliography_standalone_header_at_end_is_truncated(self):
        """
        Verify that a genuine standalone 'References' header in the latter half of document
        truncates only the trailing reference list.
        """
        body_prefix = (
            "Scientific Paper Section 1\n"
            "Detailed investigation of algorithmic efficiency and empirical performance metrics. " * 10 + "\n"
        )
        bib_section = (
            "\nReferences\n"
            "1. Smith, J. (2020). Machine Learning Fundamentals.\n"
            "2. Doe, A. (2021). Deep Attention Networks."
        )
        full_paper = body_prefix + bib_section

        filtered = filter_bibliography(full_paper)
        self.assertIn("Scientific Paper Section 1", filtered)
        self.assertNotIn("Smith, J. (2020)", filtered)

    def test_filter_bibliography_devanagari_header(self):
        """Verify Devanagari Hindi bibliography header ('संदर्भ सूची') is recognized."""
        prefix = "शोध पत्र का मुख्य भाग और महत्वपूर्ण निष्कर्ष। " * 15 + "\n"
        bib = "\nसंदर्भ सूची\n1. कुमार, आर. (2022). हिंदी भाषा प्रसंस्करण।"
        full_paper = prefix + bib

        filtered = filter_bibliography(full_paper)
        self.assertIn("शोध पत्र का मुख्य भाग", filtered)
        self.assertNotIn("कुमार, आर. (2022)", filtered)

    def test_filter_quotes_bounded_quotes_removed(self):
        """Verify that standard quoted text under 250 words is cleanly filtered."""
        text = 'The author stated, "this exact phrase is directly quoted from prior published literature" in chapter 2.'
        filtered = filter_quotes(text)
        self.assertNotIn("this exact phrase is directly quoted", filtered)
        self.assertIn("The author stated,", filtered)
        self.assertIn("in chapter 2.", filtered)

    def test_filter_quotes_unclosed_quote_does_not_wipe_document(self):
        """
        Verify that an accidental unclosed quotation mark (") near the start of a document
        does NOT cause runaway regex stripping of the whole document.
        """
        malformed = (
            'The project was described as "highly innovative and disruptive.\n\n'
            'Section 2: Comprehensive Architecture Overview\n'
            'We describe the multi-tier client server model implemented for academic integrity verification. '
            'Each component is isolated to guarantee deterministic analysis. ' * 5
        )
        filtered = filter_quotes(malformed)
        self.assertIn("Section 2: Comprehensive Architecture Overview", filtered)
        self.assertIn("Each component is isolated", filtered)

    def test_is_quotation_helper_unclosed_quote_safety(self):
        """Verify _is_quotation helper does not treat everything as quote on unclosed quote."""
        ex_engine = ExclusionEngine({'exclude_quotations': True})
        passage = 'He said "Hello world and continued talking without closing quote.'
        is_quote, _ = ex_engine._is_quotation(passage, full_text=passage)
        # Should not mark entire paragraph as quoted text
        self.assertFalse(is_quote)

    # =========================================================================
    # Task 4: Repository & Match Query Configuration
    # =========================================================================

    def test_analysis_engine_repository_defaults(self):
        """Verify AnalysisEngine defaults include INTERNET, PUBLICATIONS, and SUBMITTED_WORKS."""
        engine = AnalysisEngine()
        self.assertIn("INTERNET", engine.search_repositories)
        self.assertIn("PUBLICATIONS", engine.search_repositories)
        self.assertIn("SUBMITTED_WORKS", engine.search_repositories)
        self.assertLessEqual(engine.min_match_words, 8)

    def test_turnitin_similarity_engine_defaults(self):
        """Verify TurnitinSimilarityPipeline has small match <= 8 and search repos enabled."""
        engine = TurnitinSimilarityPipeline()
        self.assertLessEqual(engine.exclude_small_matches, 8)
        self.assertLessEqual(engine.preprocessor.min_word_match, 8)
        self.assertIn("INTERNET", engine.search_repositories)
        self.assertIn("PUBLICATIONS", engine.search_repositories)
        self.assertIn("SUBMITTED_WORKS", engine.search_repositories)

    def test_duplicate_document_yields_nonzero_similarity_and_sources(self):
        """
        Integration test: When a document contains known duplicate text from ReferenceSource,
        it must produce a non-zero similarity score, matched passages, and populated top sources.
        """
        doc = Document.objects.create(
            title="Transformer Study with Duplications",
            uploaded_by=self.user,
            status=Document.Status.EXTRACTED,
            word_count=len(self.reference_body.split())
        )
        ExtractedText.objects.create(
            document=doc,
            content=self.reference_body,
            page_number=1,
            word_count=len(self.reference_body.split())
        )
        doc.status = Document.Status.EXTRACTED
        doc.save()

        engine = AnalysisEngine(
            search_repositories=["INTERNET", "PUBLICATIONS", "SUBMITTED_WORKS"],
            min_match_words=8
        )
        report = engine.analyze_document(doc, user=self.user)

        self.assertEqual(report.status, SimilarityReport.Status.COMPLETED)
        self.assertGreater(report.overall_similarity, 0.0)
        self.assertGreater(report.matched_words, 0)
        self.assertGreater(report.matched_passages.count(), 0)
        self.assertGreater(report.source_count, 0)

        # Inspect source breakdown
        self.assertTrue(bool(report.source_breakdown))
        self.assertGreater(len(report.source_breakdown), 0)

    # =========================================================================
    # Task 5: Top Sources Data Binding & PDF Generation
    # =========================================================================

    def test_criteria_data_binding_dual_camel_and_snake_case(self):
        """
        Verify compute_report_criteria populates both snake_case and camelCase keys:
        - top_sources and topSources with sourceName, type, similarityPercentage
        - match_groups and matchGroups with not_cited_or_quoted / notCited
        """
        doc = Document.objects.create(
            title="Binding Validation Document",
            uploaded_by=self.user,
            status=Document.Status.COMPLETED,
            word_count=100
        )
        report = SimilarityReport.objects.create(
            document=doc,
            status=SimilarityReport.Status.COMPLETED,
            overall_similarity=27.5,
            matched_words=55,
            total_words=200,
            source_count=1,
            source_breakdown=[{
                'source_id': str(self.reference_source.id),
                'name': self.reference_source.title,
                'sourceName': self.reference_source.title,
                'type': 'Publications',
                'sourceType': 'Publications',
                'matched_words': 55,
                'percentage': 27.5,
                'similarityPercentage': 27.5,
                'url': self.reference_source.url
            }]
        )
        MatchedPassage.objects.create(
            report=report,
            source=self.reference_source,
            submitted_text="Modern deep learning architectures rely heavily on transformer self-attention mechanisms",
            submitted_char_start=0,
            submitted_char_end=80,
            word_count=10,
            similarity_score=1.0,
            match_type=MatchedPassage.MatchType.EXACT,
            is_excluded=False,
            source_index=1
        )

        criteria = compute_report_criteria(report)

        # 1. Overall similarity keys
        self.assertIn('overall_similarity', criteria)
        self.assertIn('overallSimilarity', criteria)
        self.assertIn('overallSimilarityPercentage', criteria)
        self.assertEqual(criteria['overall_similarity'], 28)
        self.assertEqual(criteria['overallSimilarityPercentage'], 28)
        self.assertAlmostEqual(criteria['overall_similarity_float'], 27.5, places=1)

        # 2. Top sources dual keys
        self.assertIn('top_sources', criteria)
        self.assertIn('topSources', criteria)
        self.assertGreater(len(criteria['top_sources']), 0)
        self.assertGreater(len(criteria['topSources']), 0)

        first_src = criteria['top_sources'][0]
        self.assertEqual(first_src['name'], self.reference_source.title)
        self.assertEqual(first_src['sourceName'], self.reference_source.title)
        self.assertEqual(first_src['percentage'], 27.5)
        self.assertEqual(first_src['similarityPercentage'], 27.5)
        self.assertEqual(first_src['type'], 'Publication')
        self.assertEqual(first_src['sourceType'], 'Publication')

        # 3. Match groups dual keys
        self.assertIn('match_groups', criteria)
        self.assertIn('matchGroups', criteria)
        mg = criteria['match_groups']
        mg_dict = criteria['match_groups_dict']
        self.assertEqual(len(mg), 4)
        self.assertIn('not_cited_or_quoted', mg_dict)
        self.assertIn('notCited', mg_dict)
        self.assertGreaterEqual(mg_dict['notCited'], 1)

    def test_dynamic_turnitin_overview_pdf_generation(self):
        """
        Verify generate_turnitin_overview_pdf renders dynamic Top Sources and Match Groups
        into a valid PDF without raising exceptions.
        """
        doc = Document.objects.create(
            title="Overview PDF Test Document",
            uploaded_by=self.user,
            status=Document.Status.COMPLETED,
            word_count=500
        )
        report = SimilarityReport.objects.create(
            document=doc,
            status=SimilarityReport.Status.COMPLETED,
            overall_similarity=38.4,
            matched_words=192,
            total_words=500,
            source_count=2,
            source_breakdown=[
                {
                    'name': 'Internet Repository Source Alpha',
                    'sourceName': 'Internet Repository Source Alpha',
                    'type': 'Internet',
                    'sourceType': 'Internet',
                    'percentage': 22.1,
                    'similarityPercentage': 22.1,
                    'matched_words': 110
                },
                {
                    'name': 'Journal of Academic Computing',
                    'sourceName': 'Journal of Academic Computing',
                    'type': 'Publications',
                    'sourceType': 'Publications',
                    'percentage': 16.3,
                    'similarityPercentage': 16.3,
                    'matched_words': 82
                }
            ]
        )

        criteria = compute_report_criteria(report)
        pdf_buffer = generate_turnitin_overview_pdf(criteria)

        pdf_bytes = pdf_buffer.getvalue()
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_full_generate_pdf_report_pipeline(self):
        """Verify full generate_pdf_report pipeline completes and produces valid PDF."""
        doc = Document.objects.create(
            title="Full Report Pipeline Doc",
            uploaded_by=self.user,
            status=Document.Status.COMPLETED,
            word_count=120
        )
        ExtractedText.objects.create(
            document=doc,
            content=self.reference_body,
            page_number=1,
            word_count=len(self.reference_body.split())
        )
        report = SimilarityReport.objects.create(
            document=doc,
            status=SimilarityReport.Status.COMPLETED,
            overall_similarity=52.0,
            matched_words=62,
            total_words=120,
            source_count=1,
            source_breakdown=[{
                'name': self.reference_source.title,
                'type': 'Publications',
                'percentage': 52.0,
                'matched_words': 62
            }]
        )

        pdf_buf = generate_pdf_report(report)
        pdf_bytes = pdf_buf.getvalue()
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))
        self.assertGreater(len(pdf_bytes), 2000)
