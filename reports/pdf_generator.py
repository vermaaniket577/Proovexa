"""
Turnitin-identical PDF report generator using ReportLab.
Implements the exact layout and criteria from Turnitin academic similarity reports:
- Page 1: Cover Page (Author, File, Institution, Submission ID, Dates, Pages/Words/Chars card)
- Page 2: Integrity Overview Part 1 (Overall Similarity, Filtered items, Integrity Flags & Advisory Notice)
- Page 3: Integrity Overview Part 2 (Match Groups, Top Sources database summary, and Top Sources 1-10) [Image 1]
- Page 4: Integrity Overview Part 3 (Top Sources continuation 11-13+) [Image 2]
- Pages 5+: Integrity Submission (Document text with left-margin numbered source badges and pastel highlights)
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
from reportlab.graphics.shapes import Drawing, Rect, String, Circle, Line, Polygon, Ellipse

from .criteria import compute_report_criteria


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


class TurnitinReportCanvas(canvas.Canvas):
    """
    Two-pass canvas to calculate total page count and draw running
    headers and footers matching Turnitin reports:
    'Page X of Y - [Cover Page | Integrity Overview | Integrity Submission]'
    and 'Submission ID trn:oid:::...'
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

        # Footer (Bottom)
        draw_brand_decor(12.5 * mm)

        self.restoreState()


def _build_source_table_rows(s):
    """Constructs a 2-line source row matching Turnitin Top Sources list:
       Line 1: [Badge] [Category Pill]
       Line 2: Title/URL (left) and Percentage (right)
    """
    # 1. Colored number badge (oval pill)
    badge_d = Drawing(20, 13)
    badge_d.add(Rect(0, 0, 20, 13, rx=6.5, ry=6.5, fillColor=colors.HexColor(s['color']), strokeColor=None))
    badge_d.add(String(10, 3.2, str(s['index']), fontName='Helvetica-Bold', fontSize=7.5, fillColor=colors.white, textAnchor='middle'))

    # 2. Category pill tag (matching source's pastel tone)
    pill_bg = colors.HexColor(s.get('pill_bg', '#fce4ec'))
    pill_text = colors.HexColor(s.get('pill_text', '#be185d'))
    pill_d = Drawing(58, 13)
    pill_d.add(Rect(0, 0, 58, 13, rx=6.5, ry=6.5, fillColor=pill_bg, strokeColor=None))
    pill_d.add(String(29, 3.2, s['category'], fontName='Helvetica-Bold', fontSize=7, fillColor=pill_text, textAnchor='middle'))

    # Top line container table: Badge and Pill side by side
    top_table = Table([[badge_d, pill_d]], colWidths=[24, 65])
    top_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    # Title / Domain (Line 2 Left)
    title_p = Paragraph(
        f"<b>{s['title']}</b>",
        ParagraphStyle('SrcTitle', fontName='Helvetica-Bold', fontSize=8.5, leading=11, textColor=colors.HexColor('#000000'))
    )

    # Percentage (Line 2 Right)
    pct_p = Paragraph(
        f"<b>{s['percent']}</b>",
        ParagraphStyle('SrcPct', fontName='Helvetica-Bold', fontSize=8.5, leading=11, alignment=TA_RIGHT, textColor=colors.HexColor('#000000'))
    )

    return [
        [top_table, ""],
        [title_p, pct_p]
    ]


def _build_match_group_icon(mg):
    """Draws a crisp 15x15 vector icon matching Turnitin screenshot."""
    d = Drawing(15, 15)
    bg_color = colors.HexColor(mg['color'])
    icon_type = mg.get('icon', 'files')

    if icon_type == 'files':
        # Rounded square frame for Not Cited or Quoted (exact match with screenshot)
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


def generate_pdf_report(report):
    """
    Generate the Turnitin-styled similarity report with:
    1. Cover Page (Page 1)
    2. Integrity Overview (Page 2: Similarity score, filtering, integrity flags)
    3. Integrity Overview (Page 3: Match Groups, Top Sources breakdown & Sources 1-10) [Image 1]
    4. Integrity Overview (Page 4: Sources continuation 11-13+) [Image 2]
    5. Integrity Submission (Pages 5+: Document text with inline highlights & margin badges)
    """
    criteria = compute_report_criteria(report)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=22 * mm,
    )

    styles = getSampleStyleSheet()

    # Typography styles
    cover_author_style = ParagraphStyle(
        'CoverAuthor', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=22, leading=26,
        textColor=colors.HexColor('#0f172a'), spaceAfter=8
    )

    cover_title_style = ParagraphStyle(
        'CoverTitle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=16, leading=20,
        textColor=colors.HexColor('#1e293b'), spaceAfter=10
    )

    cover_inst_style = ParagraphStyle(
        'CoverInst', parent=styles['Normal'],
        fontName='Helvetica', fontSize=10, leading=14,
        textColor=colors.HexColor('#475569'), spaceAfter=20
    )

    h2_style = ParagraphStyle(
        'H2Style', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=12, leading=16,
        textColor=colors.HexColor('#0f172a'), spaceBefore=0, spaceAfter=8
    )

    detail_label = ParagraphStyle(
        'DetailLabel', parent=styles['Normal'],
        fontName='Helvetica', fontSize=7.5, leading=10,
        textColor=colors.HexColor('#64748b')
    )

    detail_val = ParagraphStyle(
        'DetailVal', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=8.5, leading=11,
        textColor=colors.HexColor('#0f172a')
    )

    stat_box_text = ParagraphStyle(
        'StatBoxText', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=9, leading=18,
        textColor=colors.HexColor('#1e293b')
    )

    overview_score_style = ParagraphStyle(
        'OverviewScore', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=24, leading=28,
        textColor=colors.HexColor('#0f172a'), spaceAfter=4
    )

    overview_sub_style = ParagraphStyle(
        'OverviewSub', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8.5, leading=11.5,
        textColor=colors.HexColor('#64748b'), spaceAfter=14
    )

    filtered_hdr_style = ParagraphStyle(
        'FilteredHdr', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=11, leading=15,
        textColor=colors.HexColor('#0f172a'), spaceAfter=5
    )

    filtered_item_style = ParagraphStyle(
        'FilteredItem', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8.5, leading=12.5,
        textColor=colors.HexColor('#1e293b')
    )

    story = []

    # =========================================================================
    # PAGE 1: COVER PAGE
    # =========================================================================
    story.append(SetSection("Cover Page"))
    story.append(Spacer(1, 100 * mm))  # Center content vertically

    story.append(Paragraph(criteria['author_name'], cover_author_style))
    story.append(Paragraph(criteria['file_name'], cover_title_style))
    story.append(Paragraph(f"🎓  {criteria['institution_name']}", cover_inst_style))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cbd5e1'), spaceAfter=14))
    story.append(Paragraph("Document Details", h2_style))

    # Details table: Left Column (Metadata) vs Right Column (Summary Card)
    left_meta_cells = [
        [Paragraph("Submission ID", detail_label)],
        [Paragraph(criteria['submission_id'], detail_val)],
        [Spacer(1, 3)],
        [Paragraph("Submission Date", detail_label)],
        [Paragraph(criteria['submission_date'], detail_val)],
        [Spacer(1, 3)],
        [Paragraph("Download Date", detail_label)],
        [Paragraph(criteria['download_date'], detail_val)],
        [Spacer(1, 3)],
        [Paragraph("File Name", detail_label)],
        [Paragraph(criteria['file_name'], detail_val)],
        [Spacer(1, 3)],
        [Paragraph("File Size", detail_label)],
        [Paragraph(criteria['file_size_display'], detail_val)],
    ]
    left_table = Table(left_meta_cells, colWidths=[240])
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
    right_table = Table(right_box_cells, colWidths=[140])
    right_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 16),
        ('RIGHTPADDING', (0, 0), (-1, -1), 16),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    doc_details_table = Table([[left_table, right_table]], colWidths=[310, 160])
    doc_details_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(doc_details_table)

    # =========================================================================
    # PAGE 2: INTEGRITY OVERVIEW (Score, Filters, Match Groups, Database Sources, Flags)
    # =========================================================================
    story.append(PageBreak())
    story.append(SetSection("Integrity Overview"))

    # 1. Overall Similarity Header
    score_val = criteria.get('overall_similarity_display', str(int(criteria['overall_similarity'])) + '%')
    score_display_str = f'<font size="25"><b>{score_val}</b></font>&nbsp; <font size="21"><b>Overall Similarity</b></font>'
    story.append(Paragraph(score_display_str, overview_score_style))
    story.append(Paragraph(
        "The combined total of all matches, including overlapping sources, for each database.",
        overview_sub_style
    ))

    # 2. Filtered from the Report
    story.append(Paragraph("<b>Filtered from the Report</b>", filtered_hdr_style))
    for item in criteria['filtered_from_report']:
        story.append(Paragraph(f'<font size="6.5">&#9656;</font>&nbsp; {item}', filtered_item_style))

    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cbd5e1'), spaceAfter=14))

    # 3. Integrity Flags (Left) & Advisory Callout Box (Right) on Page 2
    flags_left_rows = [
        [Paragraph("<b>Integrity Flags</b>", h2_style)],
        [Paragraph(f"<b>{criteria['flags_count']} Integrity Flags for Review</b>", ParagraphStyle('FlagHdr', fontName='Helvetica-Bold', fontSize=8.5, leading=11, textColor=colors.HexColor('#0f172a')))],
        [Paragraph("No suspicious text manipulations found." if criteria['flags_count'] == 0 else "Anomalies detected in submission text.", ParagraphStyle('FlagSub', fontName='Helvetica', fontSize=7.5, leading=10, textColor=colors.HexColor('#64748b')))],
    ]
    flags_left_table = Table(flags_left_rows, colWidths=[220])
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
        "A flag is not necessarily an indicator of a problem. However, we'd recommend you focus your attention there for further review."
    )
    advisory_p = Paragraph(advisory_text, ParagraphStyle('AdvText', fontName='Helvetica', fontSize=7, leading=9.5, textColor=colors.HexColor('#0369a1')))
    advisory_box = Table([[advisory_p]], colWidths=[240])
    advisory_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#dbeafe')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#bae6fd')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    flags_split_table = Table([[flags_left_table, advisory_box]], colWidths=[230, 244])
    flags_split_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(flags_split_table)

    # =========================================================================
    # PAGE 3: INTEGRITY OVERVIEW (PART 2 - Match Groups, Database Summary & Sources 1-10) [Image 1]
    # =========================================================================
    story.append(PageBreak())
    story.append(SetSection("Integrity Overview"))

    # Top of Page 3: Two Columns: Match Groups (Left) & Top Sources Database Breakdown (Right)
    mg_left_rows = [[Paragraph("<b>Match Groups</b>", h2_style)]]
    for mg in criteria['match_groups']:
        icon_circle = _build_match_group_icon(mg)

        title_p = Paragraph(
            f"<b>{mg['count']} {mg['name']}</b> &nbsp;{mg['percent']}",
            ParagraphStyle('MgTitle', fontName='Helvetica-Bold', fontSize=8.5, leading=11, textColor=colors.HexColor('#0f172a'))
        )
        desc_p = Paragraph(
            mg['description'],
            ParagraphStyle('MgDesc', fontName='Helvetica', fontSize=7, leading=9.5, textColor=colors.HexColor('#64748b'))
        )

        row_content = Table([[icon_circle, [title_p, desc_p]]], colWidths=[18, 226])
        row_content.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        mg_left_rows.append([row_content])

    mg_table = Table(mg_left_rows, colWidths=[250])
    mg_table.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    ts_right_rows = [[Paragraph("<b>Top Sources</b>", h2_style)]]
    for db in criteria['database_sources']:
        pct_p = Paragraph(f"<b>{db['percent']}</b>", ParagraphStyle('DbPct', fontName='Helvetica-Bold', fontSize=8.5, textColor=colors.HexColor('#0f172a')))
        icon_d = _build_database_source_icon(db)
        name_p = Paragraph(db['name'], ParagraphStyle('DbName', fontName='Helvetica', fontSize=8.5, leading=11, textColor=colors.HexColor('#1e293b')))
        row_t = Table([[pct_p, icon_d, name_p]], colWidths=[26, 18, 160])
        row_t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        ts_right_rows.append([row_t])

    ts_table = Table(ts_right_rows, colWidths=[210])
    ts_table.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    split_mg_ts_table = Table([[mg_table, ts_table]], colWidths=[260, 214])
    split_mg_ts_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(split_mg_ts_table)

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cbd5e1'), spaceAfter=8))

    # Middle of Page 3: Top Sources Section Title & Subtitle (Image 1)
    story.append(Paragraph("<b>Top Sources</b>", h2_style))
    story.append(Paragraph(
        "The sources with the highest number of matches within the submission. Overlapping sources will not be displayed.",
        overview_sub_style
    ))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cbd5e1'), spaceAfter=6))

    # Sources 1 to 10 on Page 3
    all_sources = criteria['top_sources']
    page3_sources = all_sources[:10]
    page4_sources = all_sources[10:]

    if page3_sources:
        p3_table_data = []
        for s in page3_sources:
            p3_table_data.extend(_build_source_table_rows(s))

        p3_table = Table(p3_table_data, colWidths=[420, 44])
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
    # PAGE 4: INTEGRITY OVERVIEW (PART 3 - Top Sources Continuation 11+) [Image 2]
    # =========================================================================
    story.append(PageBreak())
    story.append(SetSection("Integrity Overview"))

    if page4_sources:
        p4_table_data = []
        for s in page4_sources:
            p4_table_data.extend(_build_source_table_rows(s))

        p4_table = Table(p4_table_data, colWidths=[420, 44])
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
        fontName='Helvetica-Bold', fontSize=13, leading=17,
        textColor=colors.HexColor('#0f172a'), spaceAfter=14
    )

    doc_para_style = ParagraphStyle(
        'DocParaStyle', parent=styles['Normal'],
        fontName='Times-Roman', fontSize=10, leading=15,
        alignment=TA_JUSTIFY, spaceAfter=10
    )

    extracted_texts = report.document.extracted_texts.all().order_by('page_number', 'paragraph_number')
    matched_passages = report.matched_passages.filter(is_excluded=False).order_by('submitted_char_start')

    story.append(Paragraph(report.document.title, doc_title_style))

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

                badge_html = f'<font color="{badge_color_hex}"><b>[{top_badge_idx}]</b></font>'
                badge_para = Paragraph(badge_html, ParagraphStyle('BadgeP', fontName='Helvetica-Bold', fontSize=9, alignment=TA_CENTER))
                text_para = Paragraph(highlighted_content, doc_para_style)

                row_table = Table([[badge_para, text_para]], colWidths=[24, 450])
                row_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ]))
                story.append(row_table)
            else:
                blank_p = Paragraph("", doc_para_style)
                text_para = Paragraph(content, doc_para_style)
                row_table = Table([[blank_p, text_para]], colWidths=[24, 450])
                row_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
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
