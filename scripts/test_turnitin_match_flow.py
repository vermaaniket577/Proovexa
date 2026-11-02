"""
Verification script for Turnitin Top Sources detection and report display.
"""
import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagiarism_project.settings')
django.setup()

from documents.models import Document, ExtractedText, ReferenceSource
from analysis.engine import AnalysisEngine
from reports.criteria import compute_report_criteria
from reports.pdf_generator import generate_pdf_report
from django.contrib.auth import get_user_model

User = get_user_model()

def run_test():
    user = User.objects.first()
    print("Using user:", user.username)

    # Fetch reference sources to verify they exist
    ref_sources = ReferenceSource.objects.filter(access_limitations__contains='Turnitin')
    print(f"Total seeded Turnitin reference sources: {ref_sources.count()}")

    # Pick three sources to construct an academic text with matching passages
    s1 = ReferenceSource.objects.filter(title__icontains="spam messages").first()
    s2 = ReferenceSource.objects.filter(title__icontains="loss functions and metrics").first()
    s3 = ReferenceSource.objects.filter(title__icontains="indirect cost-related clauses").first()

    print("Source 1:", s1.title if s1 else "Missing")
    print("Source 2:", s2.title if s2 else "Missing")
    print("Source 3:", s3.title if s3 else "Missing")

    # Create a test document
    doc = Document.objects.create(
        title="Comparative Evaluation of Machine Learning Models in NLP and Contract Analysis",
        original_filename="Comparative_Evaluation_NLP.docx",
        file_type="docx",
        word_count=850,
        page_count=2,
        uploaded_by=user,
        status=Document.Status.EXTRACTED,
    )

    # Paragraph 1: Original text
    p1 = ("In recent years, artificial intelligence and deep neural network architectures have emerged as pivotal "
          "methodologies for transforming computational linguistics, industrial automation, and predictive analytics. "
          "The widespread adoption of foundation models and automated text classifiers has accelerated research into "
          "algorithmic robustness, multi-task learning, and high-dimensional semantic spaces across academic literature.")

    # Paragraph 2: Direct match with Source 1 (Spam messages)
    s1_snippet = s1.retrieved_text.split("Abstract:")[-1].strip()[:350]
    p2 = s1_snippet

    # Paragraph 3: Direct match with Source 2 (Loss functions)
    s2_snippet = s2.retrieved_text.split("Abstract:")[-1].strip()[:350]
    p3 = s2_snippet

    # Paragraph 4: Direct match with Source 3 (Indirect cost clauses)
    s3_snippet = s3.retrieved_text.split("Abstract:")[-1].strip()[:350]
    p4 = s3_snippet

    # Create ExtractedText records
    char_offset = 0
    for idx, p_text in enumerate([p1, p2, p3, p4], 1):
        t_len = len(p_text)
        ExtractedText.objects.create(
            document=doc,
            page_number=1 if idx <= 2 else 2,
            paragraph_number=idx,
            content=p_text,
            word_count=len(p_text.split()),
            char_start=char_offset,
            char_end=char_offset + t_len,
        )
        char_offset += t_len + 2

    doc.word_count = sum(len(p.split()) for p in [p1, p2, p3, p4])
    doc.save()
    print(f"Created test Document ID {doc.id} with {doc.word_count} words.")

    # Run AnalysisEngine
    engine = AnalysisEngine(exclusion_settings={'exclude_self_match': True, 'min_match_words': 14, 'check_web_sources': False})
    report = engine.analyze_document(doc, user=user)

    print("\n--- Similarity Report Results ---")
    print(f"Report ID: {report.id}")
    print(f"Status: {report.status}")
    print(f"Overall Similarity: {report.overall_similarity}%")
    print(f"Source Count: {report.source_count}")
    print(f"Matched Passages Count: {report.matched_passages.count()}")

    # Compute Criteria
    criteria = compute_report_criteria(report)
    print("\n--- Integrity Overview Criteria ---")
    print(f"Submission ID: {criteria['submission_id']}")
    print("Match Groups:")
    for mg in criteria['match_groups']:
        print(f"  - {mg['name']}: {mg['count']} ({mg['percent']})")
    
    print("Database Breakdown:")
    for db in criteria['database_sources']:
        print(f"  - {db['name']}: {db['percent']}")

    print("\nRanked Top Sources:")
    for s in criteria['top_sources']:
        print(f"  [{s['index']}] [{s['category']}] {s['title'][:55]} --> {s['percent']} (Color: {s['color']})")

    # Generate PDF
    pdf_bytes = generate_pdf_report(report)
    out_pdf_path = os.path.join(os.path.dirname(__file__), "test_turnitin_output.pdf")
    with open(out_pdf_path, "wb") as f:
        content = pdf_bytes.getvalue() if hasattr(pdf_bytes, 'getvalue') else pdf_bytes
        f.write(content)
    print(f"\nSuccessfully generated Turnitin-Style PDF report ({len(content)} bytes): {out_pdf_path}")


if __name__ == '__main__':
    run_test()
