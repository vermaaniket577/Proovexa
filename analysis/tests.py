"""
End-to-end tests for the Academic Plagiarism Detection Platform.
Tests cover:
1. User models and role permissions
2. Document creation and text extraction
3. Multi-method similarity engine (Exact, N-gram, TF-IDF, Exclusions)
4. Report generation and exports (PDF, DOCX, JSON)
5. Views and web interface accessibility
"""
import io
import json
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import User, Institution, Course, Assignment
from documents.models import Document, ExtractedText, ReferenceSource
from analysis.models import SimilarityReport, MatchedPassage, ExclusionRule, AIReport
from analysis.engine import AnalysisEngine
from analysis.ai_detector import AIDetectionEngine
from reports.pdf_generator import generate_pdf_report
from reports.docx_generator import generate_docx_report
from reports.json_exporter import generate_json_report
from reports.ai_pdf_generator import generate_ai_pdf_report


class PlagiarismPlatformTestCase(TestCase):

    def setUp(self):
        # 1. Setup Institution
        self.institution = Institution.objects.create(
            name="Test University",
            short_name="TU",
            domain="test.edu",
            is_active=True
        )

        # 2. Setup Users (Admin, Teacher, Student)
        self.admin = User.objects.create_superuser(
            username="admin_user",
            email="admin@test.edu",
            password="admin_password",
            role=User.Role.ADMIN,
            institution=self.institution
        )

        self.teacher = User.objects.create_user(
            username="teacher_user",
            email="teacher@test.edu",
            password="teacher_password",
            role=User.Role.TEACHER,
            institution=self.institution
        )

        self.student = User.objects.create_user(
            username="student_user",
            email="student@test.edu",
            password="student_password",
            role=User.Role.STUDENT,
            institution=self.institution
        )

        # 3. Setup Course and Assignment
        self.course = Course.objects.create(
            name="Distributed Systems",
            code="CS301",
            institution=self.institution,
            instructor=self.teacher
        )
        self.course.students.add(self.student)

        self.assignment = Assignment.objects.create(
            title="Assignment 1: Distributed Architectures",
            course=self.course,
            created_by=self.teacher,
            max_similarity_threshold=20
        )

        # 4. Setup Reference Source in DB
        self.reference_source = ReferenceSource.objects.create(
            title="Introduction to Distributed Systems",
            author="Dr. Leslie Lamport",
            source_type=ReferenceSource.SourceType.INSTITUTIONAL,
            institution=self.institution,
            retrieved_text=(
                "A distributed system is one in which the failure of a computer you didn't even know existed "
                "can render your own computer unusable. Distributed computing systems rely on messaging protocols "
                "across independent nodes with no shared memory or global clock."
            ),
            word_count=40
        )

    def test_user_roles_and_permissions(self):
        """Test custom User model roles and permission helper properties."""
        self.assertTrue(self.admin.is_admin)
        self.assertFalse(self.admin.is_teacher)
        self.assertFalse(self.admin.is_student)

        self.assertTrue(self.teacher.is_teacher)
        self.assertFalse(self.teacher.is_admin)

        self.assertTrue(self.student.is_student)
        self.assertFalse(self.student.is_admin)

    def test_document_creation_and_text_extraction(self):
        """Test document record creation and extracted text paragraph assignment."""
        doc = Document.objects.create(
            title="Student Essay on Distributed Nodes",
            original_filename="essay.txt",
            file_type=Document.FileType.TXT,
            file_size=1024,
            file_hash="mockhash1234567890",
            mime_type="text/plain",
            uploaded_by=self.student,
            assignment=self.assignment,
            status=Document.Status.EXTRACTED,
            word_count=60,
            page_count=1
        )

        p1 = ExtractedText.objects.create(
            document=doc,
            page_number=1,
            paragraph_number=1,
            content=(
                "Distributed computing systems rely on messaging protocols across independent nodes "
                "with no shared memory or global clock. Furthermore, Byzantine fault tolerance provides "
                "guarantees even when malicious actors are present."
            ),
            word_count=30,
            char_start=0,
            char_end=200
        )

        self.assertEqual(doc.extracted_texts.count(), 1)
        self.assertEqual(doc.extracted_texts.first().page_number, 1)

    def test_similarity_analysis_engine(self):
        """Test that the similarity engine flags matches against reference sources."""
        doc = Document.objects.create(
            title="Analysis Target Document",
            original_filename="test_paper.txt",
            file_type=Document.FileType.TXT,
            file_size=512,
            file_hash="targethash0987654321",
            mime_type="text/plain",
            uploaded_by=self.student,
            status=Document.Status.EXTRACTED,
            word_count=35,
            page_count=1
        )

        # Add text that directly contains a matching passage from the reference source
        ExtractedText.objects.create(
            document=doc,
            page_number=1,
            paragraph_number=1,
            content=(
                "Distributed computing systems rely on messaging protocols across independent nodes "
                "with no shared memory or global clock."
            ),
            word_count=17,
            char_start=0,
            char_end=120
        )

        # Run analysis engine with default exclusion settings
        engine = AnalysisEngine()
        report = engine.analyze_document(doc, user=self.student)

        self.assertEqual(report.status, SimilarityReport.Status.COMPLETED)
        self.assertGreater(report.overall_similarity, 0.0)
        self.assertEqual(report.source_count, 1)
        self.assertGreaterEqual(report.matched_passages.count(), 1)

        # Verify matched passage links to our reference source
        passage = report.matched_passages.first()
        self.assertEqual(passage.source, self.reference_source)

    def test_exclusion_logic(self):
        """Test that bibliography and direct quote exclusions function properly."""
        doc = Document.objects.create(
            title="Essay with References Section",
            original_filename="with_refs.txt",
            file_type=Document.FileType.TXT,
            file_size=512,
            file_hash="withrefs12345",
            mime_type="text/plain",
            uploaded_by=self.student,
            status=Document.Status.EXTRACTED,
            word_count=50,
            page_count=1
        )

        ExtractedText.objects.create(
            document=doc,
            page_number=1,
            paragraph_number=1,
            content="This is an original analysis of computational networks.",
            word_count=8,
            char_start=0,
            char_end=56
        )
        ExtractedText.objects.create(
            document=doc,
            page_number=1,
            paragraph_number=2,
            content=(
                "References\n"
                "Lamport, L. Introduction to Distributed Systems. Relying on messaging protocols across independent nodes."
            ),
            word_count=13,
            char_start=58,
            char_end=160
        )

        # Analysis with exclude_bibliography = True
        engine = AnalysisEngine(exclusion_settings={'exclude_bibliography': True, 'min_match_words': 5})
        report = engine.analyze_document(doc, user=self.student)

        self.assertEqual(report.status, SimilarityReport.Status.COMPLETED)

    def test_report_exporters(self):
        """Test PDF, DOCX, and JSON report generation without errors."""
        doc = Document.objects.create(
            title="Export Evaluation Document",
            original_filename="eval.txt",
            file_type=Document.FileType.TXT,
            file_size=256,
            file_hash="evalhash123",
            mime_type="text/plain",
            uploaded_by=self.student,
            status=Document.Status.COMPLETED,
            word_count=20,
            page_count=1
        )

        report = SimilarityReport.objects.create(
            document=doc,
            overall_similarity=22.5,
            total_words=20,
            matched_words=5,
            source_count=1,
            status=SimilarityReport.Status.COMPLETED,
            created_by=self.student
        )

        MatchedPassage.objects.create(
            report=report,
            submitted_text="Distributed computing systems rely on messaging protocols",
            source_text="Distributed computing systems rely on messaging protocols",
            submitted_page=1,
            submitted_paragraph=1,
            submitted_char_start=0,
            submitted_char_end=57,
            source=self.reference_source,
            match_type=MatchedPassage.MatchType.EXACT,
            similarity_score=1.0,
            word_count=7,
            source_index=1,
            is_excluded=False
        )

        # Test PDF generation
        pdf_buffer = generate_pdf_report(report)
        self.assertIsInstance(pdf_buffer, io.BytesIO)
        self.assertGreater(pdf_buffer.getbuffer().nbytes, 100)

        # Test DOCX generation
        docx_buffer = generate_docx_report(report)
        self.assertIsInstance(docx_buffer, io.BytesIO)
        self.assertGreater(docx_buffer.getbuffer().nbytes, 100)

        # Test JSON exporter
        json_data = generate_json_report(report)
        self.assertEqual(json_data['report']['id'], str(report.id))
        self.assertEqual(json_data['document']['title'], "Export Evaluation Document")
        self.assertEqual(json_data['results']['overall_similarity'], 22.5)

    def test_views_access_and_authentication(self):
        """Test web views, login access, redirects, and rendering."""
        client = Client()

        # Unauthenticated user visiting dashboard should redirect to login
        res = client.get(reverse('dashboard:home'))
        self.assertEqual(res.status_code, 302)
        self.assertIn('/accounts/login/', res.url)

        # Login as student
        client.login(username="student_user", password="student_password")

        # Student dashboard loads successfully
        res = client.get(reverse('dashboard:home'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "My Similarity Overview")

        # Upload page loads
        res = client.get(reverse('documents:upload'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Document Submission Form")

        # Documents list loads
        res = client.get(reverse('documents:list'))
        self.assertEqual(res.status_code, 200)

        # Reports list loads
        res = client.get(reverse('reports:list'))
        self.assertEqual(res.status_code, 200)

        # Admin route should redirect student to dashboard with permission message
        res = client.get(reverse('accounts:user_list'))
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, reverse('dashboard:home'))

        # Login as admin
        client.login(username="admin_user", password="admin_password")

        # Admin dashboard loads
        res = client.get(reverse('dashboard:home'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "System Administration Dashboard")

        # Admin can access user list and audit log
        res = client.get(reverse('accounts:user_list'))
        self.assertEqual(res.status_code, 200)

        res = client.get(reverse('accounts:audit_log'))
        self.assertEqual(res.status_code, 200)

    def test_ai_detection_and_reporting(self):
        """Test AI writing detection, web report, and PDF generation."""
        # Create test document with AI-like prose
        ai_doc = Document.objects.create(
            title="Generative AI in Modern Pedagogy",
            original_filename="ai_paper.docx",
            file_type="docx",
            file_size=1024,
            status=Document.Status.COMPLETED,
            uploaded_by=self.student,
            word_count=120,
            page_count=1,
        )

        content = (
            "It is important to note that artificial intelligence plays a crucial role in modern pedagogy. "
            "Furthermore, delving into the rich tapestry of intelligent tutoring systems serves as a testament to neural architectures. "
            "In conclusion, cognitive engagement remains paramount."
        )
        ExtractedText.objects.create(
            document=ai_doc,
            page_number=1,
            paragraph_number=1,
            content=content,
            word_count=len(content.split()),
            char_start=0,
            char_end=len(content),
        )

        # 1. Run AI detection engine
        engine = AIDetectionEngine()
        ai_report = engine.analyze_document(ai_doc, user=self.student)

        self.assertIsNotNone(ai_report)
        self.assertEqual(ai_report.status, AIReport.Status.COMPLETED)
        self.assertGreater(ai_report.overall_ai_score, 0.0)
        self.assertGreater(ai_report.ai_sentence_count, 0)
        self.assertTrue(len(ai_report.sentences_data) >= 3)

        # 2. Test PDF generation
        pdf_buf = generate_ai_pdf_report(ai_report)
        self.assertIsNotNone(pdf_buf)
        pdf_bytes = pdf_buf.getvalue()
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

        # 3. Test web views
        client = Client()
        client.login(username="student_user", password="student_password")

        # View AI report HTML
        res_view = client.get(reverse('reports:ai_report', args=[ai_doc.id]))
        self.assertEqual(res_view.status_code, 200)
        self.assertContains(res_view, "AI Writing Report")
        self.assertContains(res_view, f"{ai_report.overall_ai_score:.0f}%")

        # Download AI PDF
        res_pdf = client.get(reverse('reports:download_ai_pdf', args=[ai_report.id]))
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf['Content-Type'], 'application/pdf')
        self.assertGreater(len(res_pdf.content), 1000)

    def test_one_click_services_and_quick_scan_view(self):
        """Test unified 1-click generation services and view."""
        from analysis.services import generate_both_reports

        doc = Document.objects.create(
            title="1-Click Test Document",
            original_filename="one_click.txt",
            file_type=Document.FileType.TXT,
            file_size=1024,
            file_hash="hash_one_click_123",
            mime_type="text/plain",
            uploaded_by=self.student,
            assignment=self.assignment,
            status=Document.Status.EXTRACTED,
            word_count=50,
            page_count=1
        )
        ExtractedText.objects.create(
            document=doc,
            page_number=1,
            paragraph_number=1,
            content=(
                "Furthermore, it is crucial to note that distributed computing systems rely on messaging protocols "
                "across independent nodes. In addition, the intricate dance of algorithms plays a vital role."
            ),
            word_count=30,
            char_start=0,
            char_end=150,
        )

        # 1. Test service directly
        sim_report, ai_report = generate_both_reports(doc, user=self.admin)
        self.assertIsNotNone(sim_report)
        self.assertIsNotNone(ai_report)
        self.assertEqual(sim_report.status, SimilarityReport.Status.COMPLETED)
        self.assertEqual(ai_report.status, AIReport.Status.COMPLETED)

        # 2. Test Document properties
        self.assertIsNotNone(doc.latest_similarity_report)
        self.assertIsNotNone(doc.latest_ai_report)
        self.assertTrue(doc.has_both_reports)

        # 3. Test quick_scan_view
        client = Client()
        client.login(username="admin_user", password="admin_password")

        # 1-click scan both
        res = client.get(reverse('analysis:quick_scan', args=[doc.id]) + '?type=both')
        self.assertEqual(res.status_code, 302)

        # 1-click scan with custom next
        res_next = client.get(
            reverse('analysis:quick_scan', args=[doc.id]) + f'?type=both&next={reverse("documents:list")}'
        )
        self.assertEqual(res_next.status_code, 302)
        self.assertEqual(res_next.url, reverse("documents:list"))

    def test_admin_panel_one_click_endpoints(self):
        """Test Django Admin 1-click generation URLs and actions."""
        doc = Document.objects.create(
            title="Admin 1-Click Document",
            original_filename="admin_doc.txt",
            file_type=Document.FileType.TXT,
            file_size=1024,
            file_hash="hash_admin_123",
            mime_type="text/plain",
            uploaded_by=self.student,
            assignment=self.assignment,
            status=Document.Status.EXTRACTED,
            word_count=40,
            page_count=1
        )
        ExtractedText.objects.create(
            document=doc,
            page_number=1,
            paragraph_number=1,
            content=(
                "Distributed systems rely on messaging protocols across independent nodes. "
                "A comprehensive understanding is of paramount importance."
            ),
            word_count=20,
            char_start=0,
            char_end=100,
        )

        client = Client()
        client.login(username="admin_user", password="admin_password")

        # Test admin 1-click URL
        res = client.get(reverse('admin:documents_document_generate_both', args=[doc.id]))
        self.assertEqual(res.status_code, 302)

        # Test admin changelist view contains 1-click buttons
        changelist_res = client.get(reverse('admin:documents_document_changelist'))
        self.assertEqual(changelist_res.status_code, 200)
        self.assertContains(changelist_res, "1-Click Both Reports")

