"""
Turnitin-identical AI Writing Detection PDF Report Generator using ReportLab.
Implements the exact layout and criteria from Turnitin AI reports:
- Page 1: AI Writing Cover Page (Author, File, Institution, Document Details, Pages/Words/Chars card)
- Page 2: AI Writing Overview (Score, Caution card, AI-generated group row, Disclaimer)
- Pages 3+: AI Writing Submission (Document text with cyan highlights on AI sentences)
"""
import io
import os
import re
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, Flowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Rect, String, Circle, Line, Polygon, Ellipse


def _register_turnitin_fonts():
    """Register Arial TrueType fonts from system if available, falling back to Helvetica."""
    windir = os.environ.get('WINDIR', 'C:\\Windows')
    font_map = {
        'Arial': os.path.join(windir, 'Fonts', 'arial.ttf'),
        'Arial-Bold': os.path.join(windir, 'Fonts', 'arialbd.ttf'),
        'Arial-Italic': os.path.join(windir, 'Fonts', 'ariali.ttf'),
        'Arial-BoldItalic': os.path.join(windir, 'Fonts', 'arialbi.ttf'),
    }
    for name, path in font_map.items():
        if os.path.exists(path) and name not in pdfmetrics.getRegisteredFontNames():
            try:
                pdfmetrics.registerFont(TTFont(name, path))
            except Exception:
                pass

    if 'Arial' in pdfmetrics.getRegisteredFontNames() and 'Arial-Bold' in pdfmetrics.getRegisteredFontNames():
        return 'Arial', 'Arial-Bold', 'Arial-Italic'
    return 'Helvetica', 'Helvetica-Bold', 'Helvetica-Oblique'


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
    canv.setLineWidth(1.2)
    canv.setLineCap(1)
    canv.setLineJoin(1)

    # 1. Outer bracket
    p = canv.beginPath()
    p.moveTo(x + 1.5, y + 6.0)
    p.lineTo(x + 1.5, y + 10.5)
    p.curveTo(x + 1.5, y + 12.0, x + 2.5, y + 13.0, x + 4.0, y + 13.0)
    p.lineTo(x + 7.5, y + 13.0)
    p.curveTo(x + 9.0, y + 13.0, x + 10.0, y + 12.0, x + 10.0, y + 10.5)
    p.lineTo(x + 10.0, y + 2.5)
    p.curveTo(x + 10.0, y + 1.0, x + 9.0, y + 0.0, x + 7.5, y + 0.0)
    p.lineTo(x + 5.5, y + 0.0)
    canv.drawPath(p, stroke=1, fill=0)

    # 2. Curved ascending arrow
    p2 = canv.beginPath()
    p2.moveTo(x + 0.5, y + 0.0)
    p2.curveTo(x + 0.5, y + 3.0, x + 2.0, y + 5.0, x + 5.5, y + 6.5)
    canv.drawPath(p2, stroke=1, fill=0)

    # Arrow head
    p3 = canv.beginPath()
    p3.moveTo(x + 3.0, y + 6.5)
    p3.lineTo(x + 5.5, y + 6.5)
    p3.lineTo(x + 5.5, y + 4.0)
    canv.drawPath(p3, stroke=1, fill=0)

    canv.restoreState()


class AICanvas(canvas.Canvas):
    """
    Two-pass canvas for AI Writing report running header/footer.
    Coordinates: Standard A4 (595.28 x 841.89 pt), margins 36 pt.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pages = []
        self.submission_id = ""
        self.current_section = "AI Writing Cover Page"

    def showPage(self):
        page_dict = dict(self.__dict__)
        page_dict['page_section'] = self.current_section
        self.pages.append(page_dict)
        self._startPage()

    def save(self):
        page_count = len(self.pages)
        for page in self.pages:
            self.__dict__.update(page)
            section = page.get('page_section', 'AI Writing Overview')
            self.draw_decorations(page_count, section)
            super().showPage()
        super().save()

    def draw_decorations(self, total_pages, section):
        page_num = self._pageNumber
        self.saveState()

        sub_str = f"Submission ID  {self.submission_id}"

        # Resolve logo image path (official Turnitin logo mark + wordmark with TM)
        logo_path = os.path.join(os.path.dirname(__file__), 'turnitin_header_logo.png')
        if not os.path.exists(logo_path):
            logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'images', 'turnitin_header_logo.png')

        def draw_brand_decor(y_base, y_img):
            f_reg, f_bold, _ = _register_turnitin_fonts()
            # Turnitin logo mark + wordmark (exact 55.0 pt x 16.48 pt at x = 36.0 pt)
            if os.path.exists(logo_path):
                self.drawImage(logo_path, 36.0, y_img, width=55.0, height=16.48, mask='auto')
            else:
                _draw_turnitin_logo_canvas(self, 36.0, y_base - 2.0)
                self.setFont(f_bold, 8.5)
                self.setFillColor(colors.HexColor('#012e38'))
                self.drawString(50.0, y_base + 1.0, "turnitin")

            # Page and Section info at x = 107.0 pt (6.0 pt, #191919)
            self.setFont(f_reg, 6.0)
            self.setFillColor(colors.HexColor('#191919'))
            self.drawString(107.0, y_base, f"Page {page_num} of {total_pages} - {section}")

            # Submission ID right-aligned at right margin x = 559.28 pt (A4 width 595.28 - 36.0 pt)
            self.drawRightString(559.28, y_base, sub_str)

        # Header (Top of A4: height 841.89 pt): baseline y = 806.0 pt, logo y = 801.0 pt
        draw_brand_decor(806.0, 801.0)

        # Footer (Bottom of A4): baseline y = 32.5 pt, logo y = 27.52 pt
        draw_brand_decor(32.5, 27.52)

        self.restoreState()


def generate_ai_pdf_report(ai_report):
    """
    Generate an AI Writing Detection PDF report matching Turnitin format.
    """
    doc_obj = ai_report.document
    uploaded_by = doc_obj.uploaded_by
    author_name = uploaded_by.get_full_name() or uploaded_by.username or "Student Author"
    inst_name = getattr(uploaded_by.institution, 'name', '') if getattr(uploaded_by, 'institution', None) else 'Metropolitan Academic Institute'

    num_seed = abs(hash(str(ai_report.id))) % 900000000 + 100000000
    submission_id = f"trn:oid:::5:{num_seed}"

    sub_date = (doc_obj.uploaded_at or ai_report.created_at).strftime('%b %d, %Y, %I:%M %p GMT+1')
    download_date = datetime.now().strftime('%b %d, %Y, %I:%M %p GMT+1')

    # Character count
    extracted_texts = doc_obj.extracted_texts.all()
    if extracted_texts.exists():
        char_count = sum(len(t.content) for t in extracted_texts)
    else:
        char_count = (doc_obj.word_count or 100) * 6

    word_count = doc_obj.word_count or 1
    page_count = doc_obj.page_count or 1
    file_size_display = doc_obj.file_size_display if hasattr(doc_obj, 'file_size_display') else f"{doc_obj.file_size / 1024:.1f} KB"

    buffer = io.BytesIO()
    # Standard A4: 595.28 x 841.89 pt. Margins: 36.0 pt each side. Usable width: 523.28 pt.
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36.0,
        leftMargin=36.0,
        topMargin=48.0,
        bottomMargin=48.0,
    )

    styles = getSampleStyleSheet()
    f_reg, f_bold, f_italic = _register_turnitin_fonts()

    # Exact Typography styles from Turnitin samples (Inter/Arial)
    # 0% detected as AI: Inter or Arial, Bold/Semibold, ~22–23 px (17.0 pt)
    # Caution/Disclaimer headers: Inter or Arial, Semibold, ~14 px (10.5 pt)
    # Description and body items: Inter or Arial, Regular, ~10–11 px (7.8–8.0 pt)
    cover_author_style = ParagraphStyle(
        'AICoverAuthor', parent=styles['Normal'],
        fontName=f_bold, fontSize=20.0, leading=24.0,
        textColor=colors.HexColor('#191919'), spaceAfter=8
    )

    cover_title_style = ParagraphStyle(
        'AICoverTitle', parent=styles['Normal'],
        fontName=f_bold, fontSize=17.0, leading=21.0,
        textColor=colors.HexColor('#191919'), spaceAfter=10
    )

    cover_inst_style = ParagraphStyle(
        'AICoverInst', parent=styles['Normal'],
        fontName=f_reg, fontSize=8.0, leading=12.0,
        textColor=colors.HexColor('#636363'), spaceAfter=16
    )

    h2_style = ParagraphStyle(
        'AIH2', parent=styles['Normal'],
        fontName=f_bold, fontSize=10.5, leading=14.0,
        textColor=colors.HexColor('#191919'), spaceBefore=0, spaceAfter=6
    )

    detail_label = ParagraphStyle(
        'AIDetailLabel', parent=styles['Normal'],
        fontName=f_reg, fontSize=7.8, leading=10.0,
        textColor=colors.HexColor('#636363')
    )

    detail_val = ParagraphStyle(
        'AIDetailVal', parent=styles['Normal'],
        fontName=f_bold, fontSize=7.8, leading=10.0,
        textColor=colors.HexColor('#191919')
    )

    stat_box_text = ParagraphStyle(
        'AIStatBoxText', parent=styles['Normal'],
        fontName=f_bold, fontSize=7.8, leading=16.0,
        textColor=colors.HexColor('#191919')
    )

    story = []

    # =========================================================================
    # PAGE 1: AI WRITING COVER PAGE
    # =========================================================================
    story.append(SetSection("AI Writing Cover Page"))
    story.append(Spacer(1, 280))  # Positions author at y ~ 336 pt from top

    story.append(Paragraph(author_name, cover_author_style))
    story.append(Paragraph(doc_obj.original_filename, cover_title_style))

    # Mortarboard graduation cap icon + Institution name
    inst_icon = Drawing(16, 11)
    inst_icon.add(Polygon([8, 10.5, 14, 7.5, 8, 4.5, 2, 7.5], fillColor=colors.HexColor('#636363'), strokeColor=None))
    inst_icon.add(Rect(5.5, 2.0, 5.0, 3.0, rx=0.5, ry=0.5, fillColor=colors.HexColor('#636363'), strokeColor=None))
    inst_p = Paragraph(inst_name, cover_inst_style)
    inst_table = Table([[inst_icon, inst_p]], colWidths=[20, 503.28])
    inst_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
    ]))
    story.append(inst_table)

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceAfter=12))
    story.append(Paragraph("Document Details", h2_style))

    # Details table: Left Column (Metadata) vs Right Column (Summary Card)
    # Total width = 523.28 pt (348.28 + 175.0)
    left_meta_cells = [
        [Paragraph("Submission Date", detail_label)],
        [Paragraph(sub_date, detail_val)],
        [Spacer(1, 4)],
        [Paragraph("Download Date", detail_label)],
        [Paragraph(download_date, detail_val)],
        [Spacer(1, 4)],
        [Paragraph("File Name", detail_label)],
        [Paragraph(doc_obj.original_filename, detail_val)],
        [Spacer(1, 4)],
        [Paragraph("File Size", detail_label)],
        [Paragraph(file_size_display, detail_val)],
    ]
    left_table = Table(left_meta_cells, colWidths=[348.28])
    left_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))

    right_box_cells = [
        [Paragraph(f"{page_count} Pages", stat_box_text)],
        [Paragraph(f"{word_count:,} Words", stat_box_text)],
        [Paragraph(f"{char_count:,} Characters", stat_box_text)],
    ]
    right_table = Table(right_box_cells, colWidths=[175.0])
    right_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 16),
        ('RIGHTPADDING', (0, 0), (-1, -1), 16),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    doc_details_table = Table([[left_table, right_table]], colWidths=[348.28, 175.0])
    doc_details_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(doc_details_table)

    # =========================================================================
    # PAGE 2: AI WRITING OVERVIEW (Matching Exact Turnitin Sample)
    # =========================================================================
    story.append(PageBreak())
    story.append(SetSection("AI Writing Overview"))

    score_display = f"{int(ai_report.overall_ai_score)}%"

    # Top Section: Left Score + Subtext (261.64 pt), Right Caution Box (261.64 pt)
    score_heading_style = ParagraphStyle(
        'AIScoreHeading', parent=styles['Normal'],
        fontName=f_bold, fontSize=17.0, leading=22.0,
        textColor=colors.HexColor('#191919'), spaceAfter=6
    )
    score_desc_style = ParagraphStyle(
        'AIScoreDesc', parent=styles['Normal'],
        fontName=f_reg, fontSize=7.8, leading=10.5,
        textColor=colors.HexColor('#191919')
    )

    left_cells = [
        [Paragraph(f"<b>{score_display} detected as AI</b>", score_heading_style)],
        [Paragraph(
            "The percentage indicates the combined amount of likely AI-generated text as "
            "well as likely AI-generated text that was also likely revised by AI.",
            score_desc_style
        )]
    ]
    left_table = Table(left_cells, colWidths=[261.64])
    left_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 14),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    caution_title_style = ParagraphStyle(
        'AICautionTitle', parent=styles['Normal'],
        fontName=f_bold, fontSize=10.5, leading=14.0,
        textColor=colors.HexColor('#2d2d2d'), spaceAfter=4
    )
    caution_body_style = ParagraphStyle(
        'AICautionBody', parent=styles['Normal'],
        fontName=f_reg, fontSize=7.8, leading=10.5,
        textColor=colors.HexColor('#2d2d2d')
    )

    caution_cells = [
        [Paragraph("<b>Caution: Review required.</b>", caution_title_style)],
        [Paragraph(
            "It is essential to understand the limitations of AI detection before making decisions "
            "about a student's work. We encourage you to learn more about Turnitin's AI detection "
            "capabilities before using the tool.",
            caution_body_style
        )]
    ]
    caution_table = Table(caution_cells, colWidths=[255.0])
    caution_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#dbeafe')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#bae6fd')),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    overview_top_table = Table([[left_table, caution_table]], colWidths=[261.64, 261.64])
    overview_top_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(overview_top_table)

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceAfter=12))

    # Middle Section: AI-generated group row with icon
    ai_icon = Drawing(15, 15)
    ai_icon.add(Rect(0, 0, 15, 15, rx=3.5, ry=3.5, fillColor=colors.HexColor('#0084ff'), strokeColor=None))
    # Sparkle / AI vector star inside
    ai_icon.add(Circle(7.5, 7.5, 3.0, fillColor=colors.white, strokeColor=None))

    ai_grp_title = Paragraph(
        f"<b>{ai_report.ai_sentence_count} AI-generated &nbsp;{score_display}</b>",
        ParagraphStyle('AIGrpTitle', fontName=f_bold, fontSize=7.8, leading=10.5, textColor=colors.HexColor('#191919'))
    )
    ai_grp_desc = Paragraph(
        "Likely generated or likely generated and revised by AI.",
        ParagraphStyle('AIGrpDesc', fontName=f_reg, fontSize=7.8, leading=10.5, textColor=colors.HexColor('#636363'))
    )

    ai_grp_table = Table([[ai_icon, [ai_grp_title, ai_grp_desc]]], colWidths=[20, 503.28])
    ai_grp_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(ai_grp_table)

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceAfter=12))

    # Bottom Section: Disclaimer
    disclaimer_title_style = ParagraphStyle(
        'AIDisclaimerTitle', parent=styles['Normal'],
        fontName=f_bold, fontSize=10.5, leading=14.0,
        textColor=colors.HexColor('#191919'), spaceAfter=4
    )
    disclaimer_body_style = ParagraphStyle(
        'AIDisclaimerBody', parent=styles['Normal'],
        fontName=f_reg, fontSize=7.8, leading=10.5,
        textColor=colors.HexColor('#636363')
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
    # =========================================================================
    story.append(PageBreak())
    story.append(SetSection("AI Writing Submission"))

    doc_title_style = ParagraphStyle(
        'AIDocTitle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=12.0, leading=16.0,
        textColor=colors.HexColor('#191919'), spaceAfter=4
    )
    doc_sub_style = ParagraphStyle(
        'AIDocSub', parent=styles['Normal'],
        fontName='Helvetica', fontSize=7.0, leading=10.0,
        textColor=colors.HexColor('#636363'), spaceAfter=12
    )
    doc_para_style = ParagraphStyle(
        'AIDocPara', parent=styles['Normal'],
        fontName='Times-Roman', fontSize=11.04, leading=14.5,
        alignment=TA_JUSTIFY, spaceAfter=8
    )

    story.append(Paragraph(doc_obj.title, doc_title_style))
    story.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor('#0084ff'), spaceAfter=8))
    story.append(Paragraph(
        "Sentences highlighted in cyan indicate language patterns consistent with AI generation.",
        doc_sub_style
    ))

    sentences_data = ai_report.sentences_data or []
    if sentences_data:
        # Group sentences into paragraphs of ~4 sentences each or respect line breaks
        para_sentences = []
        for s in sentences_data:
            sent_text = s['sentence'].strip()
            is_ai = s['is_ai']
            if is_ai:
                para_sentences.append(f'<font backcolor="#cffafe">{sent_text}</font>')
            else:
                para_sentences.append(sent_text)

        # Render paragraphs
        chunk_size = 4
        for i in range(0, len(para_sentences), chunk_size):
            chunk = " ".join(para_sentences[i:i + chunk_size])
            story.append(Paragraph(chunk, doc_para_style))
    else:
        extracted = doc_obj.extracted_texts.all().order_by('page_number', 'paragraph_number')
        if extracted.exists():
            for et in extracted:
                story.append(Paragraph(et.content, doc_para_style))
        else:
            story.append(Paragraph("No text content available.", doc_para_style))

    def canvas_maker(*args, **kwargs):
        c = AICanvas(*args, **kwargs)
        c.submission_id = submission_id
        return c

    doc.build(story, canvasmaker=canvas_maker)
    buffer.seek(0)
    return buffer
