"""
Turnitin-style AI Writing Detection PDF Report Generator.
Generates an official AI report with:
- Page 1: AI Writing Cover Page
- Page 2: AI Writing Overview (Matching exact Turnitin screenshot with score, caution box & disclaimer)
- Pages 3+: AI Writing Submission (Cyan highlights on suspected AI sentences with [AI] badge)
"""
import io
import re
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, Flowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas


class SetSection(Flowable):
    """Zero-size flowable to dynamically instruct canvas of current section name."""
    def __init__(self, section_name):
        super().__init__()
        self.section_name = section_name
        self.width = 0
        self.height = 0

    def wrap(self, availWidth, availHeight):
        return 0, 0

    def draw(self):
        self.canv.current_section = self.section_name


def _draw_turnitin_logo_canvas(canv, x, y):
    """Draws the authentic Turnitin brand vector mark on the canvas at (x, y)."""
    canv.saveState()
    canv.setStrokeColor(colors.HexColor('#0084ff'))
    canv.setLineWidth(1.3)
    canv.setLineCap(1)
    canv.setLineJoin(1)

    # 1. Outer bracket
    p = canv.beginPath()
    p.moveTo(x + 0.6 * mm, y + 2.2 * mm)
    p.lineTo(x + 0.6 * mm, y + 3.8 * mm)
    p.curveTo(x + 0.6 * mm, y + 4.4 * mm, x + 1.0 * mm, y + 4.8 * mm, x + 1.6 * mm, y + 4.8 * mm)
    p.lineTo(x + 2.8 * mm, y + 4.8 * mm)
    p.curveTo(x + 3.4 * mm, y + 4.8 * mm, x + 3.8 * mm, y + 4.4 * mm, x + 3.8 * mm, y + 3.8 * mm)
    p.lineTo(x + 3.8 * mm, y + 0.8 * mm)
    p.curveTo(x + 3.8 * mm, y + 0.2 * mm, x + 3.4 * mm, y - 0.2 * mm, x + 2.8 * mm, y - 0.2 * mm)
    p.lineTo(x + 2.1 * mm, y - 0.2 * mm)
    canv.drawPath(p, stroke=1, fill=0)

    # 2. Curved ascending arrow
    p2 = canv.beginPath()
    p2.moveTo(x + 0.2 * mm, y - 0.2 * mm)
    p2.curveTo(x + 0.2 * mm, y + 1.0 * mm, x + 0.8 * mm, y + 1.8 * mm, x + 2.2 * mm, y + 2.3 * mm)
    canv.drawPath(p2, stroke=1, fill=0)

    # Arrow head
    p3 = canv.beginPath()
    p3.moveTo(x + 1.1 * mm, y + 2.3 * mm)
    p3.lineTo(x + 2.2 * mm, y + 2.3 * mm)
    p3.lineTo(x + 2.2 * mm, y + 1.2 * mm)
    canv.drawPath(p3, stroke=1, fill=0)

    canv.restoreState()


class AICanvas(canvas.Canvas):
    """Two-pass canvas for AI Writing report running header/footer."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pages = []
        self.submission_id = ""
        self.current_section = "AI Writing Cover Page"
        self.page_sections = {}

    def showPage(self):
        self.page_sections[self._pageNumber] = getattr(self, 'current_section', 'AI Writing Overview')
        self.pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self.pages)
        for page in self.pages:
            self.__dict__.update(page)
            self.draw_decorations(page_count)
            super().showPage()
        super().save()

    def draw_decorations(self, total_pages):
        page_num = self._pageNumber
        section = self.page_sections.get(page_num, "AI Writing Overview")

        self.saveState()
        sub_str = f"Submission ID  {self.submission_id}"

        def draw_brand_decor(y_base):
            x_icon = 18 * mm
            _draw_turnitin_logo_canvas(self, x_icon, y_base)

            # "turnitin" in dark slate/petrol teal #012e38
            self.setFont('Helvetica-Bold', 10)
            self.setFillColor(colors.HexColor('#012e38'))
            self.drawString(x_icon + 5.2 * mm, y_base + 0.5 * mm, "turnitin")

            # Page and Section info
            self.setFont('Helvetica', 8.5)
            self.setFillColor(colors.HexColor('#475569'))
            self.drawString(x_icon + 24 * mm, y_base + 0.5 * mm, f"Page {page_num} of {total_pages} - {section}")

            # Submission ID right-aligned
            self.setFont('Helvetica', 8.5)
            self.setFillColor(colors.HexColor('#475569'))
            self.drawRightString(192 * mm, y_base + 0.5 * mm, sub_str)

        # Header (Top)
        draw_brand_decor(281 * mm)

        # Thin divider line under header on all pages (matching Turnitin official style)
        self.setStrokeColor(colors.HexColor('#cbd5e1'))
        self.setLineWidth(0.5)
        self.line(18 * mm, 276 * mm, 192 * mm, 276 * mm)

        # Footer (Bottom)
        draw_brand_decor(12.5 * mm)

        self.restoreState()


def generate_ai_pdf_report(ai_report):
    """
    Generate an AI Writing Detection PDF report matching Turnitin format.
    """
    doc_obj = ai_report.document
    uploaded_by = doc_obj.uploaded_by
    author_name = uploaded_by.get_full_name() or uploaded_by.username or "Student Author"
    inst_name = getattr(uploaded_by.institution, 'name', 'Academic Institute') if getattr(uploaded_by, 'institution', None) else 'Academic Institute'

    num_seed = abs(hash(str(ai_report.id))) % 900000000 + 100000000
    submission_id = f"trn:oid:::1:{num_seed}"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=26 * mm,
        bottomMargin=22 * mm,
    )

    styles = getSampleStyleSheet()

    cover_author_style = ParagraphStyle(
        'AICoverAuthor', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=22, leading=26,
        textColor=colors.HexColor('#0f172a'), spaceAfter=8
    )

    cover_title_style = ParagraphStyle(
        'AICoverTitle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=16, leading=20,
        textColor=colors.HexColor('#1e293b'), spaceAfter=10
    )

    cover_inst_style = ParagraphStyle(
        'AICoverInst', parent=styles['Normal'],
        fontName='Helvetica', fontSize=10, leading=14,
        textColor=colors.HexColor('#475569'), spaceAfter=20
    )

    h2_style = ParagraphStyle(
        'AIH2', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=12, leading=16,
        textColor=colors.HexColor('#0f172a'), spaceBefore=8, spaceAfter=8
    )

    detail_label = ParagraphStyle(
        'AIDetailLabel', parent=styles['Normal'],
        fontName='Helvetica', fontSize=7.5, leading=10,
        textColor=colors.HexColor('#64748b')
    )

    detail_val = ParagraphStyle(
        'AIDetailVal', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=8.5, leading=11,
        textColor=colors.HexColor('#0f172a')
    )

    story = []

    # =========================================================================
    # PAGE 1: AI WRITING COVER PAGE
    # =========================================================================
    story.append(SetSection("AI Writing Cover Page"))
    story.append(Spacer(1, 95 * mm))
    story.append(Paragraph(author_name, cover_author_style))
    story.append(Paragraph(doc_obj.original_filename, cover_title_style))
    story.append(Paragraph(f"🎓  {inst_name}", cover_inst_style))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cbd5e1'), spaceAfter=14))
    story.append(Paragraph("Document Details", h2_style))

    sub_date = (doc_obj.uploaded_at or ai_report.created_at).strftime('%b %d, %Y, %I:%M %p GMT+1')
    now_date = datetime.now().strftime('%b %d, %Y, %I:%M %p GMT+1')

    left_cells = [
        [Paragraph("Submission ID", detail_label)],
        [Paragraph(submission_id, detail_val)],
        [Spacer(1, 3)],
        [Paragraph("Submission Date", detail_label)],
        [Paragraph(sub_date, detail_val)],
        [Spacer(1, 3)],
        [Paragraph("Download Date", detail_label)],
        [Paragraph(now_date, detail_val)],
        [Spacer(1, 3)],
        [Paragraph("File Name", detail_label)],
        [Paragraph(doc_obj.original_filename, detail_val)],
    ]
    left_table = Table(left_cells, colWidths=[240])
    left_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    score_display = "*" if ai_report.overall_ai_score == 0 else f"{ai_report.overall_ai_score:.0f}%"

    right_cells = [
        [Paragraph(f"<font size='18' color='#0284c7'><b>{score_display}</b></font>", ParagraphStyle('ScoreBig', alignment=TA_CENTER))],
        [Paragraph("<b>detected as AI</b>", ParagraphStyle('ScoreSub', fontName='Helvetica-Bold', fontSize=8.5, alignment=TA_CENTER, textColor=colors.HexColor('#0369a1')))],
        [Spacer(1, 4)],
        [Paragraph(f"{ai_report.ai_sentence_count} of {ai_report.total_sentences} Sentences Flagged", ParagraphStyle('SentencesP', fontName='Helvetica', fontSize=8, alignment=TA_CENTER, textColor=colors.HexColor('#475569')))],
    ]
    right_box = Table(right_cells, colWidths=[150])
    right_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e0f2fe')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#bae6fd')),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    cover_details_table = Table([[left_table, right_box]], colWidths=[310, 160])
    cover_details_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(cover_details_table)

    # =========================================================================
    # PAGE 2: AI WRITING OVERVIEW (Matching Exact Turnitin Screenshot)
    # =========================================================================
    story.append(PageBreak())
    story.append(SetSection("AI Writing Overview"))

    score_heading_style = ParagraphStyle(
        'AIScoreHeading',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=colors.HexColor('#000000'),
        spaceAfter=10
    )
    score_desc_style = ParagraphStyle(
        'AIScoreDesc',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14.5,
        textColor=colors.HexColor('#0f172a'),
    )

    left_cells = [
        [Paragraph(f"<b>{score_display} detected as AI</b>", score_heading_style)],
        [Paragraph(
            "The percentage indicates the combined amount of likely AI-generated text as well as likely AI-generated text that was also likely revised by AI.",
            score_desc_style
        )]
    ]
    left_table = Table(left_cells, colWidths=[240])
    left_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 16),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    caution_title_style = ParagraphStyle(
        'AICautionTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=8
    )
    caution_body_style = ParagraphStyle(
        'AICautionBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=13,
        textColor=colors.HexColor('#1e293b'),
    )

    caution_cells = [
        [Paragraph("<b>Caution: Review required.</b>", caution_title_style)],
        [Paragraph(
            "It is essential to understand the limitations of AI detection before making decisions about a student's work. "
            "We encourage you to learn more about Turnitin's AI detection capabilities before using the tool.",
            caution_body_style
        )]
    ]
    caution_table = Table(caution_cells, colWidths=[210])
    caution_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e0f2fe')),
        ('ROUNDEDCORNERS', [10, 10, 10, 10]),
        ('TOPPADDING', (0, 0), (-1, -1), 16),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 16),
        ('LEFTPADDING', (0, 0), (-1, -1), 16),
        ('RIGHTPADDING', (0, 0), (-1, -1), 16),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    overview_table = Table([[left_table, caution_table]], colWidths=[250, 220])
    overview_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
    ]))
    story.append(overview_table)

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cbd5e1'), spaceBefore=8, spaceAfter=22))

    # Disclaimer Section (Bottom)
    disclaimer_title_style = ParagraphStyle(
        'AIDisclaimerTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor('#000000'),
        spaceAfter=6
    )
    disclaimer_body_style = ParagraphStyle(
        'AIDisclaimerBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=12.5,
        textColor=colors.HexColor('#000000'),
    )

    story.append(Paragraph("<b>Disclaimer</b>", disclaimer_title_style))
    disclaimer_text = (
        "Our AI writing assessment is designed to help educators identify text that might be prepared by a generative AI tool. "
        "Our AI writing assessment may not always be accurate (it may misidentify writing that is likely human generated as AI generated "
        "and likely AI generated as human generated) so it should not be used as the sole basis for adverse actions against a student. "
        "It takes further scrutiny and human judgment in conjunction with an organization's application of its specific academic policies "
        "to determine whether any academic misconduct has occurred."
    )
    story.append(Paragraph(disclaimer_text, disclaimer_body_style))

    # =========================================================================
    # PAGES 3+: AI HIGHLIGHTED SUBMISSION
    # Flagged sentences highlighted in signature Turnitin Cyan/Light Blue
    # =========================================================================
    story.append(PageBreak())
    story.append(SetSection("AI Writing Submission"))
    story.append(Spacer(1, 10))

    story.append(Paragraph(f"<b>{doc_obj.title}</b>", h2_style))
    story.append(Paragraph(
        "Sentences highlighted in cyan indicate language patterns consistent with AI generation.",
        ParagraphStyle('SubIntro', fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#64748b'), spaceAfter=14)
    ))

    sentences_data = ai_report.sentences_data or []
    if sentences_data:
        for s in sentences_data:
            sent_text = s['sentence']
            is_ai = s['is_ai']
            conf = s.get('confidence', 0.5)

            if is_ai:
                badge_p = Paragraph(
                    f'<font color="#0284c7"><b>[AI]</b></font>',
                    ParagraphStyle('AIBadge', fontName='Helvetica-Bold', fontSize=8, alignment=TA_CENTER)
                )
                text_p = Paragraph(
                    f'<font backcolor="#cffafe">{sent_text}</font>',
                    ParagraphStyle('AIText', fontName='Times-Roman', fontSize=10, leading=15, alignment=TA_JUSTIFY)
                )
            else:
                badge_p = Paragraph("", ParagraphStyle('BlankB'))
                text_p = Paragraph(
                    sent_text,
                    ParagraphStyle('HumanText', fontName='Times-Roman', fontSize=10, leading=15, alignment=TA_JUSTIFY)
                )

            row_table = Table([[badge_p, text_p]], colWidths=[24, 440])
            row_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(row_table)
    else:
        story.append(Paragraph("No sentence breakdown data available.", ParagraphStyle('NoData', fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#64748b'))))

    def canvas_maker(*args, **kwargs):
        c = AICanvas(*args, **kwargs)
        c.submission_id = submission_id
        return c

    doc.build(story, canvasmaker=canvas_maker)
    buffer.seek(0)
    return buffer
