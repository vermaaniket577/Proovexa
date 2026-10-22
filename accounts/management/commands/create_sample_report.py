"""
Create a sample document submission and run a real similarity scan
so the system has active reports ready for viewing and export.
"""
from django.core.management.base import BaseCommand
from accounts.models import User
from documents.models import Document, ExtractedText, ReferenceSource
from analysis.engine import AnalysisEngine


class Command(BaseCommand):
    help = 'Creates a realistic sample document and executes similarity analysis'

    def handle(self, *args, **options):
        student = User.objects.filter(role=User.Role.STUDENT).first()
        if not student:
            self.stdout.write(self.style.ERROR("No student found. Run seed_data first."))
            return

        doc, created = Document.objects.get_or_create(
            title="Analysis of Distributed Fault Tolerance in Modern Cloud Clusters",
            uploaded_by=student,
            defaults={
                'original_filename': "cloud_distributed_systems_draft.docx",
                'file_type': Document.FileType.DOCX,
                'file_size': 48290,
                'file_hash': "sample_cloud_paper_hash_897123",
                'mime_type': "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                'page_count': 3,
                'word_count': 380,
                'status': Document.Status.EXTRACTED,
            }
        )

        ExtractedText.objects.filter(document=doc).delete()

        # Paragraph 1: Original text
        ExtractedText.objects.create(
            document=doc,
            page_number=1,
            paragraph_number=1,
            content=(
                "Cloud computing infrastructures have evolved dramatically over the past two decades. "
                "Modern enterprises increasingly depend on decentralized server architectures to deliver "
                "high-availability services to millions of concurrent users globally."
            ),
            word_count=32,
            char_start=0,
            char_end=220
        )

        # Paragraph 2: High overlap with ReferenceSource #1
        ExtractedText.objects.create(
            document=doc,
            page_number=1,
            paragraph_number=2,
            content=(
                "Distributed computing systems are composed of autonomous computational entities "
                "that communicate and coordinate their actions solely by message passing. "
                "The primary benefits of distributed systems include horizontal scalability, "
                "enhanced fault tolerance through redundancy, and lower latency through geographic distribution. "
                "However, designing distributed algorithms requires addressing fundamental challenges "
                "including consensus in asynchronous networks, network partitioning, and clock synchronization."
            ),
            word_count=65,
            char_start=222,
            char_end=670
        )

        # Paragraph 3: Partial match with ReferenceSource #2
        ExtractedText.objects.create(
            document=doc,
            page_number=2,
            paragraph_number=1,
            content=(
                "When preparing technical documentation, researchers must adhere to scholarly conventions. "
                "In educational settings, institutional integrity mandates that all referenced concepts "
                "be appropriately documented with citations. Automated similarity detection software provides "
                "an objective baseline by identifying textual alignment against corpus indices."
            ),
            word_count=43,
            char_start=672,
            char_end=1010
        )

        # Paragraph 4: Quoted text that can be excluded or highlighted
        ExtractedText.objects.create(
            document=doc,
            page_number=2,
            paragraph_number=2,
            content=(
                "As noted by theoretical computer scientists: \"According to Brewer's CAP theorem, "
                "a distributed data store can simultaneously provide at most two out of three guarantees: "
                "consistency, availability, and partition tolerance.\""
            ),
            word_count=31,
            char_start=1012,
            char_end=1240
        )

        # Paragraph 5: Bibliography section
        ExtractedText.objects.create(
            document=doc,
            page_number=3,
            paragraph_number=1,
            content=(
                "References\n"
                "1. Pendelton, A. (2023). Principles of Distributed Systems and Cloud Scalability. Academic Press.\n"
                "2. Vance, M. (2024). Academic Research Integrity and Plagiarism in Higher Education."
            ),
            word_count=32,
            char_start=1242,
            char_end=1470
        )

        doc.word_count = 203
        doc.page_count = 3
        doc.status = Document.Status.EXTRACTED
        doc.save()

        # Run analysis
        engine = AnalysisEngine(exclusion_settings={
            'exclude_bibliography': True,
            'exclude_quotations': True,
            'exclude_citations': True,
            'min_match_words': 5,
            'exclude_self_match': True,
        })
        report = engine.analyze_document(doc, user=student)

        self.stdout.write(self.style.SUCCESS(
            f"Created sample report ID: {report.id} for document '{doc.title}' with {report.overall_similarity:.1f}% similarity!"
        ))
