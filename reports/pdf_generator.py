"""
Turnitin-identical PDF report generator using ReportLab.
Implements the exact layout and criteria from Turnitin academic similarity reports:
- Page 1: Cover Page (Author, File, Institution, Document Details, Pages/Words/Chars card)
- Page 2: Integrity Overview Part 1 (Overall Similarity, Filtered items, Match Groups, Top Sources database breakdown, Integrity Flags & Advisory Notice)
- Page 3: Integrity Overview Part 2 (Match Groups & Top Sources snapshot, Top Sources title/desc, and Top Sources 1-10)
- Page 4: Integrity Overview Part 3 (Top Sources continuation 11-13+)
- Pages 5+: Integrity Submission (Document text with left-margin numbered source badges and pastel highlights)
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

from .criteria import compute_report_criteria


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


# Palette for source numbering and highlights (Turnitin signature colors)
SOURCE_PALETTE = [
    ('#e91e63', '#fce4ec'),  # 1: Pink/Magenta
    ('#1976d2', '#e3f2fd'),  # 2: Blue
    ('#2e7d32', '#e8f5e9'),  # 3: Green
    ('#7b1fa2', '#f3e5f5'),  # 4: Purple
    ('#c2185b', '#fce4ec'),  # 5: Rose
    ('#0288d1', '#e1f5fe'),  # 6: Sky Blue
    ('#00897b', '#e0f2f1'),  # 7: Teal
    ('#5e35b1', '#ede7f6'),  # 8: Deep Purple
    ('#d81b60', '#fce4ec'),  # 9: Magenta
    ('#0d47a1', '#e8eaf6'),  # 10: Dark Blue
    ('#ec407a', '#f8bbd0'),  # 11: Soft Pink
    ('#1565c0', '#bbdefb'),  # 12: Royal Blue
    ('#00695c', '#b2dfdb'),  # 13: Pine
]


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


class TurnitinReportCanvas(canvas.Canvas):
    """
    Two-pass canvas to calculate total page count and draw running
    headers and footers matching Turnitin reports:
    'Page X of Y - [Cover Page | Integrity Overview | Integrity Submission]'
    and 'Submission ID trn:oid:::...'
    Coordinates: Standard A4 (595.28 x 841.89 pt), margins 36 pt.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pages = []
        self.current_section = "Cover Page"
        self.submission_id = ""

    def showPage(self):
        page_dict = dict(self.__dict__)
        page_dict['page_section'] = self.current_section
        self.pages.append(page_dict)
        self._startPage()

    def save(self):
        page_count = len(self.pages)
        for page in self.pages:
            self.__dict__.update(page)
            section = page.get('page_section', 'Integrity Overview')
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


def _build_source_table_rows(s):
    """Constructs a 2-line source row matching Turnitin Top Sources list:
       Line 1: [Badge] [Category Pill]
       Line 2: Title/URL (left) and Percentage (right)
       Total width: 540 pt (colWidths: 490, 50)
    """
    f_reg, f_bold, _ = _register_turnitin_fonts()
    # 1. Colored number badge (oval pill)
    badge_d = Drawing(16, 11)
    badge_d.add(Rect(0, 0, 16, 11, rx=5.5, ry=5.5, fillColor=colors.HexColor(s['color']), strokeColor=None))
    badge_d.add(String(8, 2.8, str(s['index']), fontName=f_bold, fontSize=7.0, fillColor=colors.white, textAnchor='middle'))

    # 2. Category pill tag (matching source's pastel tone)
    pill_bg = colors.HexColor(s.get('pill_bg', '#fce4ec'))
    pill_text = colors.HexColor(s.get('pill_text', '#be185d'))
    pill_d = Drawing(52, 11)
    pill_d.add(Rect(0, 0, 52, 11, rx=5.5, ry=5.5, fillColor=pill_bg, strokeColor=None))
    pill_d.add(String(26, 2.8, s['category'], fontName=f_bold, fontSize=7.0, fillColor=pill_text, textAnchor='middle'))

    # Top line container table: Badge and Pill side by side
    top_table = Table([[badge_d, pill_d]], colWidths=[20, 60])
    top_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    # Title / Domain (Line 2 Left: width 490 pt)
    title_p = Paragraph(
        f"<b>{s['title']}</b>",
        ParagraphStyle('SrcTitle', fontName=f_bold, fontSize=8.0, leading=10.5, textColor=colors.HexColor('#191919'))
    )

    # Percentage (Line 2 Right: width 50 pt)
    pct_p = Paragraph(
        f"<b>{s['percent']}</b>",
        ParagraphStyle('SrcPct', fontName=f_bold, fontSize=8.0, leading=10.5, alignment=TA_RIGHT, textColor=colors.HexColor('#191919'))
    )

    return [
        [top_table, ""],
        [title_p, pct_p]
    ]


def _build_match_group_icon(mg):
    """Draws a crisp 15x15 vector icon matching Turnitin match groups."""
    d = Drawing(15, 15)
    bg_color = colors.HexColor(mg['color'])
    icon_type = mg.get('icon', 'files')

    if icon_type == 'files':
        # Rounded square frame for Not Cited or Quoted
        d.add(Rect(0, 0, 15, 15, rx=3.5, ry=3.5, fillColor=bg_color, strokeColor=None))
        # Overlapping document sheets
        d.add(Rect(3.8, 4.8, 5, 6.5, rx=0.5, ry=0.5, fillColor=colors.white, strokeColor=None))
        d.add(Rect(6.2, 3.2, 5, 6.5, rx=0.5, ry=0.5, fillColor=colors.white, strokeColor=bg_color, strokeWidth=0.4))
    else:
        d.add(Circle(7.5, 7.5, 7.5, fillColor=bg_color, strokeColor=None))
        if icon_type == 'quote':
            # Quotation marks
            d.add(String(7.5, 3.8, '\u201c \u201d', fontName='Helvetica-Bold', fontSize=8, fillColor=colors.white, textAnchor='middle'))
        elif icon_type == 'citation':
            # Horizontal citation lines
            d.add(Line(4.2, 9.2, 10.8, 9.2, strokeColor=colors.white, strokeWidth=1.0))
            d.add(Line(4.2, 7.2, 10.8, 7.2, strokeColor=colors.white, strokeWidth=1.0))
            d.add(Line(4.2, 5.2, 8.8, 5.2, strokeColor=colors.white, strokeWidth=1.0))
        elif icon_type == 'mortarboard':
            # Graduation mortarboard cap
            d.add(Polygon([7.5, 10.8, 11.8, 8.5, 7.5, 6.2, 3.2, 8.5], fillColor=colors.white, strokeColor=None))
            d.add(Rect(5.2, 4.2, 4.6, 2.3, rx=0.4, ry=0.4, fillColor=colors.white, strokeColor=None))

    return d


def _build_database_source_icon(db):
    """Draws a clean vector icon for database categories (Internet, Publications, Submitted works)."""
    d = Drawing(12, 12)
    icon_type = db.get('icon', 'globe')
    slate = colors.HexColor('#64748b')

    if icon_type == 'globe':
        # Globe icon
        d.add(Circle(6, 6, 4.8, fillColor=None, strokeColor=slate, strokeWidth=0.7))
        d.add(Line(1.2, 6, 10.8, 6, strokeColor=slate, strokeWidth=0.7))
        d.add(Ellipse(6, 6, 2.4, 4.8, fillColor=None, strokeColor=slate, strokeWidth=0.7))
    elif icon_type == 'book':
        # Open book icon
        d.add(Rect(1.5, 2.2, 4.0, 7.2, rx=0.5, ry=0.5, fillColor=None, strokeColor=slate, strokeWidth=0.7))
        d.add(Rect(6.5, 2.2, 4.0, 7.2, rx=0.5, ry=0.5, fillColor=None, strokeColor=slate, strokeWidth=0.7))
    elif icon_type == 'person':
        # Student silhouette icon
        d.add(Circle(6, 8.2, 2.0, fillColor=slate, strokeColor=None))
        d.add(Polygon([2.5, 2.2, 9.5, 2.2, 8.6, 5.2, 3.4, 5.2], fillColor=slate, strokeColor=None))

    return d


def _build_arrow_bullet():
    """Draws a crisp authentic right-pointing vector triangle for filtered items matching Turnitin's geometry."""
    d = Drawing(10, 8)
    d.add(Polygon([2.5, 2.0, 6.0, 4.0, 2.5, 6.0], fillColor=colors.HexColor('#191919'), strokeColor=None))
    return d


def generate_pdf_report(report):
    """
    Generate the Turnitin-styled similarity report with:
    1. Cover Page (Page 1)
    2. Integrity Overview (Page 2: Similarity score, filtering, match groups, database sources, flags)
    3. Integrity Overview (Page 3: Match Groups & Top Sources snapshot & Sources 1-10)
    4. Integrity Overview (Page 4: Sources continuation 11-13+)
    5. Integrity Submission (Pages 5+: Document text with inline highlights & margin badges)
    """
    criteria = compute_report_criteria(report)

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
    # 2% Overall Similarity: Inter or Arial, Bold/Semibold, ~22–23 px (17.0 pt)
    # Filtered from the Report: Inter or Arial, Semibold, ~14 px (10.5 pt)
    # Description and list items: Inter or Arial, Regular, ~10–11 px (7.8–8.0 pt)
    cover_author_style = ParagraphStyle(
        'CoverAuthor', parent=styles['Normal'],
        fontName=f_bold, fontSize=20.0, leading=24.0,
        textColor=colors.HexColor('#191919'), spaceAfter=8
    )

    cover_title_style = ParagraphStyle(
        'CoverTitle', parent=styles['Normal'],
        fontName=f_bold, fontSize=17.0, leading=21.0,
        textColor=colors.HexColor('#191919'), spaceAfter=10
    )

    cover_inst_style = ParagraphStyle(
        'CoverInst', parent=styles['Normal'],
        fontName=f_reg, fontSize=8.0, leading=12.0,
        textColor=colors.HexColor('#636363'), spaceAfter=16
    )

    h2_style = ParagraphStyle(
        'H2Style', parent=styles['Normal'],
        fontName=f_bold, fontSize=10.5, leading=14.0,
        textColor=colors.HexColor('#191919'), spaceBefore=0, spaceAfter=6
    )

    detail_label = ParagraphStyle(
        'DetailLabel', parent=styles['Normal'],
        fontName=f_reg, fontSize=7.8, leading=10.0,
        textColor=colors.HexColor('#636363')
    )

    detail_val = ParagraphStyle(
        'DetailVal', parent=styles['Normal'],
        fontName=f_bold, fontSize=7.8, leading=10.0,
        textColor=colors.HexColor('#191919')
    )

    stat_box_text = ParagraphStyle(
        'StatBoxText', parent=styles['Normal'],
        fontName=f_bold, fontSize=7.8, leading=16.0,
        textColor=colors.HexColor('#191919')
    )

    overview_score_style = ParagraphStyle(
        'OverviewScore', parent=styles['Normal'],
        fontName=f_bold, fontSize=17.0, leading=21.0,
        textColor=colors.HexColor('#191919'), spaceAfter=3.0
    )

    overview_sub_style = ParagraphStyle(
        'OverviewSub', parent=styles['Normal'],
        fontName=f_reg, fontSize=7.0, leading=10.0,
        textColor=colors.HexColor('#636363'), spaceAfter=18.0
    )

    filtered_hdr_style = ParagraphStyle(
        'FilteredHdr', parent=styles['Normal'],
        fontName=f_bold, fontSize=10.0, leading=13.0,
        textColor=colors.HexColor('#191919'), spaceAfter=6.0
    )

    filtered_item_style = ParagraphStyle(
        'FilteredItem', parent=styles['Normal'],
        fontName=f_reg, fontSize=7.0, leading=10.0,
        textColor=colors.HexColor('#191919')
    )

    story = []

    # =========================================================================
    # PAGE 1: COVER PAGE
    # =========================================================================
    story.append(SetSection("Cover Page"))
    story.append(Spacer(1, 280))  # Positions author at y ~ 336 pt from top

    story.append(Paragraph(criteria['author_name'], cover_author_style))
    story.append(Paragraph(criteria['file_name'], cover_title_style))

    # Mortarboard graduation cap icon + Institution name
    inst_icon = Drawing(16, 11)
    inst_icon.add(Polygon([8, 10.5, 14, 7.5, 8, 4.5, 2, 7.5], fillColor=colors.HexColor('#636363'), strokeColor=None))
    inst_icon.add(Rect(5.5, 2.0, 5.0, 3.0, rx=0.5, ry=0.5, fillColor=colors.HexColor('#636363'), strokeColor=None))
    inst_p = Paragraph(criteria['institution_name'], cover_inst_style)
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
        [Paragraph(criteria['submission_date'], detail_val)],
        [Spacer(1, 4)],
        [Paragraph("Download Date", detail_label)],
        [Paragraph(criteria['download_date'], detail_val)],
        [Spacer(1, 4)],
        [Paragraph("File Name", detail_label)],
        [Paragraph(criteria['file_name'], detail_val)],
        [Spacer(1, 4)],
        [Paragraph("File Size", detail_label)],
        [Paragraph(criteria['file_size_display'], detail_val)],
    ]
    left_table = Table(left_meta_cells, colWidths=[348.28])
    left_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))

    right_box_cells = [
        [Paragraph(f"{criteria['page_count']} Pages", stat_box_text)],
        [Paragraph(f"{criteria['word_count']:,} Words", stat_box_text)],
        [Paragraph(f"{criteria['character_count']:,} Characters", stat_box_text)],
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
    # PAGE 2: INTEGRITY OVERVIEW (Part 1: Score, Filters, Match Groups, DB Breakdown, Flags)
    # =========================================================================
    story.append(PageBreak())
    story.append(SetSection("Integrity Overview"))

    # 1. Overall Similarity Header
    score_val = criteria.get('overall_similarity_display', str(int(criteria['overall_similarity'])) + '%')
    score_display_str = f"<b>{score_val} Overall Similarity</b>"
    story.append(Paragraph(score_display_str, overview_score_style))
    story.append(Paragraph(
        "The combined total of all matches, including overlapping sources, for each database.",
        overview_sub_style
    ))

    # 2. Filtered from the Report
    story.append(Paragraph("<b>Filtered from the Report</b>", filtered_hdr_style))
    for item in criteria['filtered_from_report']:
        bullet_d = _build_arrow_bullet()
        item_p = Paragraph(item, filtered_item_style)
        item_t = Table([[bullet_d, item_p]], colWidths=[12, 511.28])
        item_t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ]))
        story.append(item_t)

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceAfter=12))

    # 3. Two Columns: Match Groups (Left 261.64 pt) & Top Sources Database Breakdown (Right 261.64 pt)
    def _create_match_groups_table():
        mg_left_rows = [[Paragraph("<b>Match Groups</b>", h2_style)]]
        for mg in criteria['match_groups']:
            icon_circle = _build_match_group_icon(mg)
            title_p = Paragraph(
                f"<b>{mg['count']} {mg['name']}</b> &nbsp;{mg['percent']}",
                ParagraphStyle('MgTitle', fontName=f_bold, fontSize=7.8, leading=10.5, textColor=colors.HexColor('#191919'))
            )
            desc_p = Paragraph(
                mg['description'],
                ParagraphStyle('MgDesc', fontName=f_reg, fontSize=7.8, leading=10.5, textColor=colors.HexColor('#636363'))
            )
            row_content = Table([[icon_circle, [title_p, desc_p]]], colWidths=[18, 243.64])
            row_content.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            mg_left_rows.append([row_content])

        mg_t = Table(mg_left_rows, colWidths=[261.64])
        mg_t.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        return mg_t

    def _create_top_sources_db_table():
        ts_right_rows = [[Paragraph("<b>Top Sources</b>", h2_style)]]
        for db in criteria['database_sources']:
            pct_p = Paragraph(f"<b>{db['percent']}</b>", ParagraphStyle('DbPct', fontName=f_bold, fontSize=7.8, textColor=colors.HexColor('#191919')))
            icon_d = _build_database_source_icon(db)
            name_p = Paragraph(db['name'], ParagraphStyle('DbName', fontName=f_reg, fontSize=7.8, leading=10.5, textColor=colors.HexColor('#191919')))
            row_t = Table([[pct_p, icon_d, name_p]], colWidths=[24, 16, 221.64])
            row_t.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            ts_right_rows.append([row_t])

        ts_t = Table(ts_right_rows, colWidths=[261.64])
        ts_t.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        return ts_t

    mg_ts_split = Table([[_create_match_groups_table(), _create_top_sources_db_table()]], colWidths=[261.64, 261.64])
    mg_ts_split.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(mg_ts_split)

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceAfter=12))

    # 4. Integrity Flags (Left 261.64 pt) & Advisory Callout Box (Right 261.64 pt)
    flags_left_rows = [
        [Paragraph("<b>Integrity Flags</b>", h2_style)],
        [Paragraph(f"<b>{criteria['flags_count']} Integrity Flags for Review</b>", ParagraphStyle('FlagHdr', fontName=f_bold, fontSize=7.8, leading=10.5, textColor=colors.HexColor('#191919')))],
        [Paragraph("No suspicious text manipulations found." if criteria['flags_count'] == 0 else "Anomalies detected in submission text.", ParagraphStyle('FlagSub', fontName=f_reg, fontSize=7.8, leading=10.5, textColor=colors.HexColor('#636363')))],
    ]
    flags_left_table = Table(flags_left_rows, colWidths=[261.64])
    flags_left_table.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    advisory_text = (
        "Our system's algorithms look deeply at a document for any inconsistencies that "
        "would set it apart from a normal submission. If we notice something strange, we flag it for you to review.<br/><br/>"
        "A Flag is not necessarily an indicator of a problem. However, we'd recommend you focus your attention there for further review."
    )
    advisory_p = Paragraph(advisory_text, ParagraphStyle('AdvText', fontName=f_reg, fontSize=7.8, leading=10.5, textColor=colors.HexColor('#2c2c2c')))
    advisory_box = Table([[advisory_p]], colWidths=[255.0])
    advisory_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#dbeafe')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#bae6fd')),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    flags_split_table = Table([[flags_left_table, advisory_box]], colWidths=[261.64, 261.64])
    flags_split_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(flags_split_table)

    # =========================================================================
    # PAGE 3: INTEGRITY OVERVIEW (PART 2 - Match Groups & Database Snapshot & Sources 1-10)
    # =========================================================================
    story.append(PageBreak())
    story.append(SetSection("Integrity Overview"))

    # Top snapshot of Match Groups and Top Sources DB breakdown
    p3_mg_ts_split = Table([[_create_match_groups_table(), _create_top_sources_db_table()]], colWidths=[261.64, 261.64])
    p3_mg_ts_split.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(p3_mg_ts_split)

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceAfter=8))

    # Middle of Page 3: Top Sources Section Title & Subtitle
    story.append(Paragraph("<b>Top Sources</b>", h2_style))
    story.append(Paragraph(
        "The sources with the highest number of matches within the submission. Overlapping sources will not be displayed.",
        overview_sub_style
    ))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceAfter=6))

    # Sources 1 to 10 on Page 3
    all_sources = criteria['top_sources']
    page3_sources = all_sources[:10]
    page4_sources = all_sources[10:]

    if page3_sources:
        p3_table_data = []
        for s in page3_sources:
            p3_table_data.extend(_build_source_table_rows(s))

        p3_table = Table(p3_table_data, colWidths=[473.28, 50.0])
        p3_style = [
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]
        for i in range(len(page3_sources)):
            p3_style.extend([
                ('TOPPADDING', (0, 2 * i), (-1, 2 * i), 2),
                ('BOTTOMPADDING', (0, 2 * i), (-1, 2 * i), 0),
                ('TOPPADDING', (0, 2 * i + 1), (-1, 2 * i + 1), 1),
                ('BOTTOMPADDING', (0, 2 * i + 1), (-1, 2 * i + 1), 3),
                ('LINEBELOW', (0, 2 * i + 1), (-1, 2 * i + 1), 0.5, colors.HexColor('#e2e8f0')),
            ])
        p3_table.setStyle(TableStyle(p3_style))
        story.append(p3_table)

    # =========================================================================
    # PAGE 4: INTEGRITY OVERVIEW (PART 3 - Top Sources Continuation 11+)
    # =========================================================================
    story.append(PageBreak())
    story.append(SetSection("Integrity Overview"))

    if page4_sources:
        p4_table_data = []
        for s in page4_sources:
            p4_table_data.extend(_build_source_table_rows(s))

        p4_table = Table(p4_table_data, colWidths=[473.28, 50.0])
        p4_style = [
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]
        for i in range(len(page4_sources)):
            p4_style.extend([
                ('TOPPADDING', (0, 2 * i), (-1, 2 * i), 3),
                ('BOTTOMPADDING', (0, 2 * i), (-1, 2 * i), 0),
                ('TOPPADDING', (0, 2 * i + 1), (-1, 2 * i + 1), 1),
                ('BOTTOMPADDING', (0, 2 * i + 1), (-1, 2 * i + 1), 3),
                ('LINEBELOW', (0, 2 * i + 1), (-1, 2 * i + 1), 0.5, colors.HexColor('#e2e8f0')),
            ])
        p4_table.setStyle(TableStyle(p4_style))
        story.append(p4_table)
    else:
        story.append(Spacer(1, 10))

    # =========================================================================
    # PAGES 5+: INTEGRITY SUBMISSION
    # Document Text with left-margin numbered badges and pastel inline highlights
    # =========================================================================
    story.append(PageBreak())
    story.append(SetSection("Integrity Submission"))

    doc_title_style = ParagraphStyle(
        'DocTitleStyle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=12.0, leading=16.0,
        textColor=colors.HexColor('#191919'), spaceAfter=4
    )

    doc_para_style = ParagraphStyle(
        'DocParaStyle', parent=styles['Normal'],
        fontName='Times-Roman', fontSize=11.04, leading=14.5,
        alignment=TA_JUSTIFY, spaceAfter=8
    )

    extracted_texts = report.document.extracted_texts.all().order_by('page_number', 'paragraph_number')
    matched_passages = report.matched_passages.filter(is_excluded=False).order_by('submitted_char_start')

    story.append(Paragraph(report.document.title, doc_title_style))
    story.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor('#0084ff'), spaceAfter=14))

    # Pre-map passages to paragraph content
    if extracted_texts.exists():
        for et in extracted_texts:
            content = et.content
            # Check which matches overlap with this paragraph
            para_matches = []
            for p in matched_passages:
                if p.submitted_text and p.submitted_text.strip() in content:
                    para_matches.append(p)

            if para_matches:
                # Find matching source badge
                top_badge_idx = para_matches[0].source_index or 1
                badge_color_hex, _ = SOURCE_PALETTE[(top_badge_idx - 1) % len(SOURCE_PALETTE)]

                # Highlight the text inside paragraph
                highlighted_content = content
                for m in para_matches:
                    m_idx = m.source_index or 1
                    _, pastel_bg = SOURCE_PALETTE[(m_idx - 1) % len(SOURCE_PALETTE)]
                    esc_match = re.escape(m.submitted_text.strip())
                    replacement = f'<font backcolor="{pastel_bg}">{m.submitted_text.strip()}</font>'
                    highlighted_content = re.sub(esc_match, replacement, highlighted_content, count=1)

                badge_d = Drawing(16, 16)
                badge_d.add(Circle(8, 8, 7, fillColor=colors.HexColor(badge_color_hex), strokeColor=None))
                badge_d.add(String(8, 5.2, str(top_badge_idx), fontName=f_bold, fontSize=7.0, fillColor=colors.white, textAnchor='middle'))

                text_para = Paragraph(highlighted_content, doc_para_style)

                row_table = Table([[badge_d, text_para]], colWidths=[22.0, 501.28])
                row_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(row_table)
            else:
                blank_d = Drawing(16, 16)
                text_para = Paragraph(content, doc_para_style)
                row_table = Table([[blank_d, text_para]], colWidths=[22.0, 501.28])
                row_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(row_table)
    else:
        story.append(Paragraph("Document text content not extracted.", doc_para_style))

    # Build the document with our custom two-pass TurnitinReportCanvas
    def canvas_maker(*args, **kwargs):
        c = TurnitinReportCanvas(*args, **kwargs)
        c.submission_id = criteria['submission_id']
        return c

    doc.build(story, canvasmaker=canvas_maker)
    buffer.seek(0)
    return buffer
