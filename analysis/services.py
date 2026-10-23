"""
Unified analysis and reporting services for 1-click report generation.
"""
import logging
from django.utils import timezone
from accounts.models import AuditLog

logger = logging.getLogger(__name__)


def ensure_document_extracted(document):
    """
    Ensure the document has its text content extracted and ready for analysis.
    If pending or extracting, performs synchronous extraction.
    """
    from documents.models import Document, ExtractedText
    from documents.extractors import extract_text

    if document.status in [Document.Status.EXTRACTED, Document.Status.COMPLETED] and document.extracted_texts.exists():
        return True, ""

    try:
        document.status = Document.Status.EXTRACTING
        document.save(update_fields=['status'])

        result = extract_text(document.file.path, document.file_type)

        if result.errors:
            document.status = Document.Status.FAILED
            document.error_message = '; '.join(result.errors)
            document.save(update_fields=['status', 'error_message'])
            return False, document.error_message

        # Clear existing extracted texts if re-extracting
        document.extracted_texts.all().delete()

        char_offset = 0
        for page in result.pages:
            for para in page.get('paragraphs', []):
                text_len = len(para['text'])
                ExtractedText.objects.create(
                    document=document,
                    page_number=page.get('page_number', 1),
                    paragraph_number=para.get('para_number', 1),
                    content=para['text'],
                    word_count=len(para['text'].split()),
                    char_start=char_offset,
                    char_end=char_offset + text_len,
                )
                char_offset += text_len + 2

        document.page_count = result.page_count
        document.word_count = result.word_count
        document.status = Document.Status.EXTRACTED
        document.processed_at = timezone.now()
        document.save(update_fields=['page_count', 'word_count', 'status', 'processed_at'])
        return True, ""

    except Exception as e:
        logger.exception("Text extraction failed for document %s: %s", document.id, str(e))
        document.status = Document.Status.FAILED
        document.error_message = str(e)
        document.save(update_fields=['status', 'error_message'])
        return False, str(e)


def generate_similarity_report(document, user=None, exclusion_settings=None):
    """
    Generate or re-generate similarity plagiarism report for a document.
    """
    from analysis.engine import AnalysisEngine
    from analysis.models import SimilarityReport

    ok, error = ensure_document_extracted(document)
    if not ok:
        raise ValueError(f"Document extraction failed: {error}")

    engine = AnalysisEngine(exclusion_settings=exclusion_settings)
    report = engine.analyze_document(document, user=user)

    if user and user.is_authenticated:
        AuditLog.objects.create(
            user=user,
            action=AuditLog.Action.ANALYZE,
            resource_type='Document',
            resource_id=str(document.id),
            details={'report_id': str(report.id), 'type': 'similarity_1click'},
        )

    return report


def generate_ai_report(document, user=None):
    """
    Generate or re-generate AI writing detection report for a document.
    """
    from analysis.ai_detector import AIDetectionEngine

    ok, error = ensure_document_extracted(document)
    if not ok:
        raise ValueError(f"Document extraction failed: {error}")

    engine = AIDetectionEngine()
    ai_report = engine.analyze_document(document, user=user)

    if user and user.is_authenticated:
        AuditLog.objects.create(
            user=user,
            action=AuditLog.Action.ANALYZE,
            resource_type='Document',
            resource_id=str(document.id),
            details={'ai_report_id': str(ai_report.id), 'type': 'ai_1click'},
        )

    return ai_report


def generate_both_reports(document, user=None, exclusion_settings=None):
    """
    1-Click generation of both Similarity Plagiarism Report and AI Writing Report.
    Returns (similarity_report, ai_report).
    """
    sim_report = generate_similarity_report(document, user=user, exclusion_settings=exclusion_settings)
    ai_report = generate_ai_report(document, user=user)
    return sim_report, ai_report
