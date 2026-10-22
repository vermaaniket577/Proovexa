"""
Turnitin-identical PDF report generator using ReportLab.
Implements the exact layout and criteria from Turnitin academic similarity reports:
- Page 1: Cover Page (Author, File, Institution, Submission ID, Dates, Pages/Words/Chars card)
- Middle Pages: Integrity Submission (Document text with left-margin source badges and inline pastel highlights)
- Last Pages: Integrity Overview & Top Sources (Overall Similarity, Filtered items, Match Groups,
  Database breakdown, Integrity Flags advisory card, and ranked Top Sources list with colored circle badges)
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
    PageBreak, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas

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


class TurnitinReportCanvas(canvas.Canvas):
    """
    Two-pass canvas to calculate total page count and draw running
    headers/footers matching Turnitin reports:
    'Page X of Y - [Cover Page | Integrity Submission | Integrity Overview]'
    and 'Submission ID trn:oid:::...'
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pages = []
        self.page_sections = {}
        self.submission_id = ""

    def showPage(self):
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
        if page_num == 1:
            section = "Cover Page"
        elif page_num == 2:
            section = "Integrity Overview"
        elif page_num == total_pages:
            section = "Top Sources Breakdown"
        else:
            section = "Integrity Submission"

        self.saveState()
        self.setFont('Helvetica', 7.5)
        self.setFillColor(colors.HexColor('#64748b'))

        # Header (pages 1+)
        # Brand logo / name
        self.setFillColor(colors.HexColor('#0284c7'))
        self.circle(22 * mm, 282 * mm, 3, stroke=0, fill=1)
        self.setFont('Helvetica-Bold', 8.5)
        self.drawString(26 * mm, 280.5 * mm, "turnitin")

        self.setFont('Helvetica', 7.5)
        self.setFillColor(colors.HexColor('#64748b'))
        self.drawString(45 * mm, 280.5 * mm, f"Page {page_num} of {total_pages} - {section}")

        sub_str = f"Submission ID  {self.submission_id}"
        self.drawRightString(190 * mm, 280.5 * mm, sub_str)

        # Footer
        self.circle(22 * mm, 14 * mm, 3, stroke=0, fill=1)
        self.setFont('Helvetica-Bold', 8.5)
        self.setFillColor(colors.HexColor('#0284c7'))
        self.drawString(26 * mm, 12.5 * mm, "turnitin")

        self.setFont('Helvetica', 7.5)
        self.setFillColor(colors.HexColor('#64748b'))
        self.drawString(45 * mm, 12.5 * mm, f"Page {page_num} of {total_pages} - {section}")
        self.drawRightString(190 * mm, 12.5 * mm, sub_str)

        self.restoreState()


def generate_pdf_report(report):
    """
    Generate the Turnitin-styled similarity report with:
    1. Cover Page
    2. Integrity Submission (Document with inline highlights and left-margin source badges)
    3. Integrity Overview & Top Sources (at the last page)
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
        textColor=colors.HexColor('#0f172a'), spaceBefore=12, spaceAfter=8
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

    story = []

    # =========================================================================
    # PAGE 1: COVER PAGE (Image 1)
    # =========================================================================
    story.append(Spacer(1, 100 * mm))  # Center content vertically like Image 1

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
    # PAGE 2: INTEGRITY OVERVIEW & CRITERIA (Matching User's Uploaded Screenshot)
    # =========================================================================
    story.append(PageBreak())

    overview_score_style = ParagraphStyle(
        'OverviewScore', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=22, leading=26,
        textColor=colors.HexColor('#0f172a'), spaceAfter=3
    )

    overview_sub_style = ParagraphStyle(
        'OverviewSub', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8, leading=11,
        textColor=colors.HexColor('#64748b'), spaceAfter=14
    )

    filtered_hdr_style = ParagraphStyle(
        'FilteredHdr', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=10, leading=13,
        textColor=colors.HexColor('#0f172a'), spaceAfter=6
    )

    filtered_item_style = ParagraphStyle(
        'FilteredItem', parent=styles['Normal'],
        fontName='Helvetica', fontSize=7.5, leading=11,
        textColor=colors.HexColor('#334155')
    )

    # 1. Overall Similarity Header
    score_display_str = f"{int(criteria['overall_similarity'])}%  Overall Similarity"
    story.append(Paragraph(score_display_str, overview_score_style))
    story.append(Paragraph(
        "The combined total of all matches, including overlapping sources, for each database.",
        overview_sub_style
    ))

    # 2. Filtered from the Report
    story.append(Paragraph("Filtered from the Report", filtered_hdr_style))
    for item in criteria['filtered_from_report']:
        story.append(Paragraph(f"&gt;  {item}", filtered_item_style))

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceAfter=12))

    # 3. Match Groups (Left) & Top Sources Summary (Right)
    mg_left_rows = [[Paragraph("<b>Match Groups</b>", h2_style), ""]]
    for mg in criteria['match_groups']:
        badge_p = Paragraph(
            f'<font color="{mg["color"]}">●</font> <b>{mg["count"]} {mg["name"]}  {mg["percent"]}</b>',
            ParagraphStyle('MgTitle', fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor('#0f172a'))
        )
        desc_p = Paragraph(mg['description'], ParagraphStyle('MgDesc', fontName='Helvetica', fontSize=7, leading=9, textColor=colors.HexColor('#64748b')))
        mg_left_rows.append([badge_p])
        mg_left_rows.append([desc_p])
        mg_left_rows.append([Spacer(1, 2)])

    mg_table = Table(mg_left_rows, colWidths=[250])
    mg_table.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    ts_right_rows = [[Paragraph("<b>Top Sources</b>", h2_style)]]
    for db in criteria['database_sources']:
        db_p = Paragraph(
            f"<b>{db['percent']}</b> &nbsp;&nbsp;&nbsp; {db['name']}",
            ParagraphStyle('DbText', fontName='Helvetica', fontSize=8, leading=12, textColor=colors.HexColor('#1e293b'))
        )
        ts_right_rows.append([db_p])
        ts_right_rows.append([Spacer(1, 3)])

    ts_table = Table(ts_right_rows, colWidths=[210])
    ts_table.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    split_overview_table = Table([[mg_table, ts_table]], colWidths=[260, 214])
    split_overview_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(split_overview_table)

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceAfter=12))

    # 4. Integrity Flags (Left) & Advisory Callout Box (Right)
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

    # Move to Submission section (Pages 3+)
    story.append(PageBreak())

    # =========================================================================
    # PAGES 3+: INTEGRITY SUBMISSION (Image 5)
    # Document Text with left-margin numbered badges and pastel inline highlights
    # =========================================================================
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
                    # Apply background color tag
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

    # Move to Top Sources Listing
    story.append(PageBreak())

    # =========================================================================
    # TOP SOURCES LISTING (Images 3 & 4)
    # Numbered colored circle badges, Pill category tags, Titles, and Percentages
    # =========================================================================
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceAfter=10))
    story.append(Paragraph("<b>Top Sources</b>", h2_style))
    story.append(Paragraph(
        "The sources with the highest number of matches within the submission. Overlapping sources will not be displayed.",
        overview_sub_style
    ))

    if criteria['top_sources']:
        top_source_rows = []
        for s in criteria['top_sources']:
            # Colored circle number badge
            badge_p = Paragraph(
                f'<font color="{s["color"]}"><b>[{s["index"]}]</b></font>',
                ParagraphStyle('SrcBadge', fontName='Helvetica-Bold', fontSize=9, alignment=TA_CENTER)
            )

            # Category pill tag
            pill_color = '#fce4ec' if s['category'] == 'Internet' else ('#e0f2fe' if s['category'] == 'Publication' else '#f1f5f9')
            text_color = '#be185d' if s['category'] == 'Internet' else ('#0369a1' if s['category'] == 'Publication' else '#334155')
            pill_p = Paragraph(
                f'<font color="{text_color}"><b>{s["category"]}</b></font>',
                ParagraphStyle('SrcPill', fontName='Helvetica-Bold', fontSize=7, alignment=TA_CENTER)
            )

            # Title
            title_p = Paragraph(
                f"<b>{s['title']}</b>",
                ParagraphStyle('SrcTitle', fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor('#0f172a'))
            )

            # Percentage
            pct_p = Paragraph(
                f"<b>{s['percent']}</b>",
                ParagraphStyle('SrcPct', fontName='Helvetica-Bold', fontSize=8.5, alignment=TA_RIGHT, textColor=colors.HexColor('#0f172a'))
            )

            top_source_rows.append([badge_p, pill_p, title_p, pct_p])

        sources_table = Table(top_source_rows, colWidths=[28, 68, 320, 58])
        sources_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#f1f5f9')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ]))
        story.append(sources_table)
    else:
        story.append(Paragraph("No matching reference sources located.", ParagraphStyle('NoSrc', fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#64748b'))))

    # Build the document with our custom two-pass TurnitinReportCanvas
    def canvas_maker(*args, **kwargs):
        c = TurnitinReportCanvas(*args, **kwargs)
        c.submission_id = criteria['submission_id']
        return c

    doc.build(story, canvasmaker=canvas_maker)
    buffer.seek(0)
    return buffer
