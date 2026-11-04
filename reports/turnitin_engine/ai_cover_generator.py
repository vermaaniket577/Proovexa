"""
AI Writing Cover Page generator.
Builds the academic AI Writing Cover Page (Page 1):
- Institution name
- Document title / Original filename
- Document details table (Submission ID, dates, page count, word/char count, file size)
- Statistics summary card
"""
from io import BytesIO
import os
import pymupdf

class AICoverGenerator:
    """Generates Section 1 Cover Page matching the Turnitin AI report design."""

    @staticmethod
    def generate_cover_page(criteria: dict) -> pymupdf.Document:
        """
        Creates a Letter-sized PDF page for the AI Writing Cover Page.
        """
        doc = pymupdf.open()
        page = doc.new_page(width=612.0, height=792.0)

        # Assets
        turnitin_logo_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'static', 'images', 'turnitin', 'turnitin_logo_exact.png'
        )
        doc_icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'static', 'images', 'turnitin', 'doc_details_icon.png'
        )

        sub_id = criteria.get('submission_id', 'trn:oid:::8971:157249595')
        total_pages = criteria.get('total_pages', 17)

        # 1. Running Header
        if os.path.exists(turnitin_logo_path):
            page.insert_image(pymupdf.Rect(36.0, 24.0, 91.0, 40.5), filename=turnitin_logo_path)
        page.insert_text(pymupdf.Point(107.0, 34.0), f"Page 1 of {total_pages} - Cover Page", fontname="helv", fontsize=6.0, color=(0.1, 0.1, 0.1))
        page.insert_text(pymupdf.Point(460.67, 34.0), "Submission ID", fontname="helv", fontsize=6.0, color=(0.1, 0.1, 0.1))
        page.insert_text(pymupdf.Point(506.12, 34.0), sub_id, fontname="helv", fontsize=6.0, color=(0.1, 0.1, 0.1))

        # 2. Main Title and Institution
        # Institution
        inst_name = criteria.get('institution_name', 'University of the Immaculate Conception')
        if os.path.exists(doc_icon_path):
            page.insert_image(pymupdf.Rect(36.0, 397.0, 48.0, 409.0), filename=doc_icon_path)
        page.insert_text(pymupdf.Point(56.0, 405.5), inst_name, fontname="helv", fontsize=8.0, color=(0.2, 0.2, 0.2))

        # Original Filename
        file_name = criteria.get('file_name', 'Document.docx')
        page.insert_text(pymupdf.Point(36.0, 385.0), file_name, fontname="helv", fontsize=17.0, color=(0.1, 0.1, 0.1))

        # Thin divider below title
        shape = page.new_shape()
        shape.draw_line(pymupdf.Point(36.0, 425.0), pymupdf.Point(576.0, 425.0))
        shape.finish(color=(0.8, 0.8, 0.8), width=0.5)
        shape.commit()

        # 3. Document Details Heading
        page.insert_text(pymupdf.Point(36.0, 453.0), "Document Details", fontname="helv", fontsize=10.0, color=(0.1, 0.1, 0.1))

        # Details list
        y = 480.0
        details = [
            ("Submission ID", criteria.get('submission_id', 'trn:oid:::8971:157249595')),
            ("Submission Date", criteria.get('submission_date', 'Nov 4, 2026, 6:11 AM GMT+0')),
            ("Download Date", criteria.get('download_date', 'Nov 4, 2026, 6:17 AM GMT+0')),
            ("File Name", file_name),
            ("File Size", criteria.get('file_size_display', '204.0 KB')),
        ]
        for label, val in details:
            page.insert_text(pymupdf.Point(36.0, y), label, fontname="helv", fontsize=7.0, color=(0.4, 0.4, 0.4))
            page.insert_text(pymupdf.Point(36.0, y + 14.0), val, fontname="helv", fontsize=7.0, color=(0.1, 0.1, 0.1))
            y += 36.0

        # Right Summary Box
        box_rect = pymupdf.Rect(403.0, 470.0, 492.0, 548.0)
        shape = page.new_shape()
        shape.draw_rect(box_rect)
        shape.finish(fill=(0.972, 0.972, 0.972), color=None)
        shape.commit()

        p_count = criteria.get('page_count', 15)
        w_count = criteria.get('word_count', 4144)
        c_count = criteria.get('character_count', 24516)

        page.insert_text(pymupdf.Point(415.0, 492.0), f"{p_count} Pages", fontname="helv", fontsize=7.0, color=(0.1, 0.1, 0.1))
        page.insert_text(pymupdf.Point(415.0, 514.0), f"{w_count:,} Words", fontname="helv", fontsize=7.0, color=(0.1, 0.1, 0.1))
        page.insert_text(pymupdf.Point(415.0, 536.0), f"{c_count:,} Characters", fontname="helv", fontsize=7.0, color=(0.1, 0.1, 0.1))

        # 4. Running Footer
        if os.path.exists(turnitin_logo_path):
            page.insert_image(pymupdf.Rect(36.0, 748.0, 91.0, 764.5), filename=turnitin_logo_path)
        page.insert_text(pymupdf.Point(107.0, 757.5), f"Page 1 of {total_pages} - Cover Page", fontname="helv", fontsize=6.0, color=(0.1, 0.1, 0.1))
        page.insert_text(pymupdf.Point(460.67, 757.5), "Submission ID", fontname="helv", fontsize=6.0, color=(0.1, 0.1, 0.1))
        page.insert_text(pymupdf.Point(506.12, 757.5), sub_id, fontname="helv", fontsize=6.0, color=(0.1, 0.1, 0.1))

        return doc
