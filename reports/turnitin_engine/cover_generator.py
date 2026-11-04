"""
Cover page generator for Turnitin-style similarity reports.
Builds the formal academic cover page with institution, document details,
author, timestamps, word/character count, and Turnitin branding.
"""
import os
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

class ReportCoverGenerator:
    """Generates the Section A Cover Page using ReportLab."""

    @staticmethod
    def generate(criteria: dict) -> BytesIO:
        buf = BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=40,
            bottomMargin=40
        )
        story = []
        styles = getSampleStyleSheet()

        inst_style = ParagraphStyle(
            'InstStyle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=16,
            leading=20,
            textColor=colors.HexColor('#1f2937')
        )
        file_style = ParagraphStyle(
            'FileStyle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=12,
            leading=16,
            textColor=colors.HexColor('#4b5563')
        )
        sec_title = ParagraphStyle(
            'SecTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=14,
            leading=18,
            textColor=colors.HexColor('#111827')
        )
        lbl_style = ParagraphStyle(
            'LblStyle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#6b7280')
        )
        val_style = ParagraphStyle(
            'ValStyle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#1f2937')
        )

        story.append(Spacer(1, 15))
        story.append(Paragraph(criteria.get('institution_name', 'University of the Immaculate Conception'), inst_style))
        story.append(Spacer(1, 8))
        story.append(Paragraph(criteria.get('file_name', 'Document.docx'), file_style))
        story.append(Spacer(1, 24))

        # Thin separator
        sep = Table([['']], colWidths=[540], rowHeights=[1])
        sep.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#e5e7eb')),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(sep)
        story.append(Spacer(1, 20))

        story.append(Paragraph("Document Details", sec_title))
        story.append(Spacer(1, 12))

        # Details table
        details_data = [
            [Paragraph("Submission ID", lbl_style), Paragraph("Submission Date", lbl_style)],
            [Paragraph(criteria.get('submission_id', 'trn:oid:::8971:157249595'), val_style),
             Paragraph(criteria.get('submission_date', 'Nov 4, 2026, 6:11 AM GMT+0'), val_style)],
            [Paragraph("Download Date", lbl_style), Paragraph("File Name", lbl_style)],
            [Paragraph(criteria.get('download_date', 'Nov 4, 2026, 6:13 AM GMT+0'), val_style),
             Paragraph(criteria.get('file_name', 'Document.docx'), val_style)],
            [Paragraph("File Size", lbl_style), Paragraph("Total Pages", lbl_style)],
            [Paragraph(criteria.get('file_size_display', '204.0 KB'), val_style),
             Paragraph(f"{criteria.get('page_count', 15)} Pages", val_style)],
            [Paragraph("Word Count", lbl_style), Paragraph("Character Count", lbl_style)],
            [Paragraph(f"{criteria.get('word_count', 4144):,} Words", val_style),
             Paragraph(f"{criteria.get('character_count', 24516):,} Characters", val_style)],
        ]
        t = Table(details_data, colWidths=[270, 270])
        t.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(t)
        doc.build(story)
        buf.seek(0)
        return buf
