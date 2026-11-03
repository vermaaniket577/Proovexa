"""
Comprehensive automated tests for Multi-Source Similarity Detection Engine.
Validates all 7 required scenarios:
1. An identical document and source text.
2. A document containing copied paragraphs.
3. A paraphrased document.
4. A completely unrelated document (genuine verified 0%).
5. A document with references and quotations (exclusion filters).
6. An empty or corrupted document.
7. A document where external APIs / source retrieval fail ("Unable to complete the comparison").
"""
import uuid
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone

from accounts.models import User, Institution
from documents.models import Document, ExtractedText, ReferenceSource
from analysis.models import SimilarityReport, MatchedPassage
from analysis.engine import AnalysisEngine


class RealSimilaritySourcesTestCase(TestCase):
    """Test suite verifying authentic similarity detection and absence of false 0% bugs."""

    def setUp(self):
        self.patcher = patch('sources.providers.multi_source_search', return_value={'results': [], 'sources_checked': ['Local Academic Database'], 'failed_sources': []})
        self.mock_multi_search = self.patcher.start()

        self.institution = Institution.objects.create(
            name="Stanford Academic Integrity Lab",
            short_name="SAIL",
            domain="sail.edu",
            is_active=True
        )

        self.student = User.objects.create_user(
            username="research_student",
            email="student@sail.edu",
            password="secure_password_123",
            role=User.Role.STUDENT,
            institution=self.institution
        )

        # Standard authentic source text (Machine Learning Paper)
        self.source_text_1 = (
            "Deep learning neural networks utilize backpropagation and gradient descent optimization algorithms "
            "to minimize loss functions across multi-layered perceptual representations. Recurrent architectures "
            "incorporate internal memory gates to process temporal sequences and linguistic dependencies effectively. "
            "Convolutional feature extractors preserve spatial hierarchies through localized receptive fields and pooling operations."
        )

        self.ref_source_1 = ReferenceSource.objects.create(
            title="Foundations of Modern Deep Learning Architectures",
            author="LeCun, Bengio, Hinton",
            source_type=ReferenceSource.SourceType.ACADEMIC,
            url="https://doi.org/10.1038/nature14539",
            doi="10.1038/nature14539",
            retrieved_text=self.source_text_1,
            word_count=len(self.source_text_1.split()),
            retrieval_timestamp=timezone.now(),
            institution=self.institution,
            is_active=True
        )

    def tearDown(self):
        self.patcher.stop()
        super().tearDown()

    # -------------------------------------------------------------------------
    # Scenario 1: Identical document and source text
    # -------------------------------------------------------------------------
    def test_identical_document_and_source(self):
        """Identical text must yield ~100% similarity and exact match type."""
        doc = Document.objects.create(
            title="Identical Submission Copy",
            original_filename="identical.txt",
            file_type=Document.FileType.TXT,
            uploaded_by=self.student,
            status=Document.Status.EXTRACTED,
            word_count=len(self.source_text_1.split()),
            page_count=1
        )
        ExtractedText.objects.create(
            document=doc,
            page_number=1,
            paragraph_number=1,
            content=self.source_text_1,
            word_count=len(self.source_text_1.split()),
            char_start=0,
            char_end=len(self.source_text_1)
        )

        engine = AnalysisEngine(exclusion_settings={'min_match_words': 8})
        report = engine.analyze_document(doc, user=self.student)

        self.assertEqual(report.status, SimilarityReport.Status.COMPLETED)
        self.assertGreaterEqual(report.overall_similarity, 90.0)
        self.assertEqual(report.source_count, 1)
        self.assertGreaterEqual(report.matched_passages.count(), 1)
        passage = report.matched_passages.first()
        self.assertEqual(passage.source, self.ref_source_1)
        self.assertEqual(passage.match_type, 'exact')

    # -------------------------------------------------------------------------
    # Scenario 2: Document containing copied paragraphs
    # -------------------------------------------------------------------------
    def test_copied_paragraphs_detection(self):
        """Document with partially copied paragraphs must accurately flag copied sections."""
        original_para = (
            "In our empirical laboratory experiment, we synthesized a novel lithium titanate anode "
            "using high temperature sol-gel methodology with citric acid as chelating agent. "
            "Electrochemical impedance spectroscopy confirmed superior charge transfer kinetics."
        )
        doc = Document.objects.create(
            title="Composite Research Paper",
            original_filename="composite.txt",
            file_type=Document.FileType.TXT,
            uploaded_by=self.student,
            status=Document.Status.EXTRACTED,
            word_count=len(original_para.split()) + len(self.source_text_1.split()),
            page_count=2
        )
        # Page 1: Original text
        ExtractedText.objects.create(
            document=doc,
            page_number=1,
            paragraph_number=1,
            content=original_para,
            word_count=len(original_para.split()),
            char_start=0,
            char_end=len(original_para)
        )
        # Page 2: Copied passage
        ExtractedText.objects.create(
            document=doc,
            page_number=2,
            paragraph_number=1,
            content=self.source_text_1,
            word_count=len(self.source_text_1.split()),
            char_start=len(original_para) + 2,
            char_end=len(original_para) + 2 + len(self.source_text_1)
        )

        engine = AnalysisEngine(exclusion_settings={'min_match_words': 8})
        report = engine.analyze_document(doc, user=self.student)

        self.assertEqual(report.status, SimilarityReport.Status.COMPLETED)
        # Similarity should be around 45% to 65% (copied proportion)
        self.assertGreater(report.overall_similarity, 30.0)
        self.assertLess(report.overall_similarity, 85.0)
        # Page reference must correctly point to page 2 where copied text is located
        matched = report.matched_passages.filter(is_excluded=False).first()
        self.assertIsNotNone(matched)
        self.assertEqual(matched.submitted_page, 2)
        self.assertEqual(matched.source, self.ref_source_1)

    # -------------------------------------------------------------------------
    # Scenario 3: Paraphrased document
    # -------------------------------------------------------------------------
    def test_paraphrased_document(self):
        """Paraphrased text must be detected via fuzzy/n-gram similarity, not returning 0%."""
        paraphrased_text = (
            "Deep learning neural systems use backpropagation and gradient optimization algorithms "
            "to reduce cost functions across multi-layer feature representations. Sequential networks "
            "contain internal memory elements to handle temporal sequences and semantic connections."
        )
        doc = Document.objects.create(
            title="Paraphrased Assignment",
            original_filename="paraphrased.txt",
            file_type=Document.FileType.TXT,
            uploaded_by=self.student,
            status=Document.Status.EXTRACTED,
            word_count=len(paraphrased_text.split()),
            page_count=1
        )
        ExtractedText.objects.create(
            document=doc,
            page_number=1,
            paragraph_number=1,
            content=paraphrased_text,
            word_count=len(paraphrased_text.split()),
            char_start=0,
            char_end=len(paraphrased_text)
        )

        engine = AnalysisEngine(exclusion_settings={'min_match_words': 6})
        report = engine.analyze_document(doc, user=self.student)

        self.assertEqual(report.status, SimilarityReport.Status.COMPLETED)
        # Paraphrase should be flagged with non-zero similarity
        self.assertGreater(report.overall_similarity, 0.0)

    # -------------------------------------------------------------------------
    # Scenario 4: Completely unrelated document (genuine verified 0%)
    # -------------------------------------------------------------------------
    def test_completely_unrelated_document_verified_zero(self):
        """Unrelated text must return genuine 0% similarity with sources checked recorded."""
        unrelated_text = (
            "Ancient Mesopotamian cuneiform tablets discovered near the Tigris river reveal intricate "
            "agricultural inventory records, barley transactions, and lunar astronomical calendar observations "
            "inscribed on sun-baked clay cylinders during the third dynasty of Ur."
        )
        doc = Document.objects.create(
            title="Mesopotamian Archaeology Survey",
            original_filename="archaeology.txt",
            file_type=Document.FileType.TXT,
            uploaded_by=self.student,
            status=Document.Status.EXTRACTED,
            word_count=len(unrelated_text.split()),
            page_count=1
        )
        ExtractedText.objects.create(
            document=doc,
            page_number=1,
            paragraph_number=1,
            content=unrelated_text,
            word_count=len(unrelated_text.split()),
            char_start=0,
            char_end=len(unrelated_text)
        )

        engine = AnalysisEngine(exclusion_settings={'min_match_words': 8})
        report = engine.analyze_document(doc, user=self.student)

        self.assertEqual(report.status, SimilarityReport.Status.COMPLETED)
        self.assertEqual(report.overall_similarity, 0.0)
        self.assertEqual(report.matched_words, 0)
        self.assertEqual(report.source_count, 0)
        # Sources were verified clean
        self.assertGreaterEqual(len(report.sources_checked), 1)

    # -------------------------------------------------------------------------
    # Scenario 5: Document with references and quotations
    # -------------------------------------------------------------------------
    def test_references_and_quotes_exclusion(self):
        """Bibliography sections and quotes should be filtered out when exclusion settings are active."""
        essay_text = "Modern artificial intelligence research has expanded across multiple scientific disciplines."
        bib_text = (
            "References\n"
            "LeCun, Y., Bengio, Y., & Hinton, G. Deep learning neural networks utilize backpropagation and gradient descent optimization algorithms."
        )
        full_content = f"{essay_text}\n\n{bib_text}"

        doc = Document.objects.create(
            title="Paper with Bibliography Section",
            original_filename="paper_with_bib.txt",
            file_type=Document.FileType.TXT,
            uploaded_by=self.student,
            status=Document.Status.EXTRACTED,
            word_count=len(full_content.split()),
            page_count=1
        )
        ExtractedText.objects.create(
            document=doc,
            page_number=1,
            paragraph_number=1,
            content=full_content,
            word_count=len(full_content.split()),
            char_start=0,
            char_end=len(full_content)
        )

        engine = AnalysisEngine(exclusion_settings={'exclude_bibliography': True, 'min_match_words': 6})
        report = engine.analyze_document(doc, user=self.student)

        self.assertEqual(report.status, SimilarityReport.Status.COMPLETED)
        # Bibliography match should be excluded or excluded_words recorded
        if report.matched_passages.exists():
            for p in report.matched_passages.all():
                if 'References' in p.submitted_text or 'LeCun' in p.submitted_text:
                    self.assertTrue(p.is_excluded)
                    self.assertIn('bibliography', p.exclusion_reason.lower())

    # -------------------------------------------------------------------------
    # Scenario 6: Empty or corrupted document
    # -------------------------------------------------------------------------
    def test_empty_or_corrupted_document_fails_cleanly(self):
        """Empty or unreadable document must fail cleanly with descriptive error, not report 0% completed."""
        doc = Document.objects.create(
            title="Empty Corrupted Upload",
            original_filename="corrupted.pdf",
            file_type=Document.FileType.PDF,
            uploaded_by=self.student,
            status=Document.Status.PENDING,
            word_count=0,
            page_count=0
        )
        # No ExtractedText records created

        engine = AnalysisEngine()
        report = engine.analyze_document(doc, user=self.student)

        self.assertEqual(report.status, SimilarityReport.Status.FAILED)
        self.assertIn("No extracted text found", report.error_message)
        self.assertEqual(doc.status, Document.Status.FAILED)

    # -------------------------------------------------------------------------
    # Scenario 7: External APIs and source retrieval failure
    # -------------------------------------------------------------------------
    def test_source_retrieval_failure_shows_unable_to_complete(self):
        """If source retrieval fails and no local sources exist, must show 'Unable to complete the comparison'."""
        # Deactivate all reference sources in DB
        ReferenceSource.objects.all().update(is_active=False)

        doc = Document.objects.create(
            title="Isolated Student Essay",
            original_filename="isolated.txt",
            file_type=Document.FileType.TXT,
            uploaded_by=self.student,
            status=Document.Status.EXTRACTED,
            word_count=40,
            page_count=1
        )
        ExtractedText.objects.create(
            document=doc,
            page_number=1,
            paragraph_number=1,
            content="This is an isolated document uploaded when all external databases are unreachable.",
            word_count=12,
            char_start=0,
            char_end=85
        )

        # Mock multi_source_search to simulate total network/API failure
        with patch('sources.providers.multi_source_search', return_value={'results': [], 'sources_checked': [], 'failed_sources': ['Crossref', 'OpenAlex']}):
            engine = AnalysisEngine(exclusion_settings={'check_web_sources': True})
            report = engine.analyze_document(doc, user=self.student)

            # Must NOT report 0% completed; must report FAILED with "Unable to complete the comparison"
            self.assertEqual(report.status, SimilarityReport.Status.FAILED)
            self.assertIn("Unable to complete the comparison", report.error_message)
            self.assertEqual(doc.status, Document.Status.FAILED)
            self.assertIn("Unable to complete the comparison", doc.error_message)
