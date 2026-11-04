"""
PDF Merger for Turnitin-style reports.
Combines Cover + Overview pages with Highlighted Original Document submission pages.
"""
from io import BytesIO
import pymupdf

class PDFReportMerger:
    """Merges ReportLab overview sections with PyMuPDF submission document."""

    @staticmethod
    def merge(overview_pdf: pymupdf.Document, submission_pdf: pymupdf.Document) -> BytesIO:
        merged = pymupdf.open()
        merged.insert_pdf(overview_pdf)
        merged.insert_pdf(submission_pdf)

        buf = BytesIO()
        merged.save(buf)
        buf.seek(0)
        return buf
