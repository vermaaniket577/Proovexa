"""
AI Writing Overview generator.
Builds the dynamic AI Writing Overview page (Page 2):
- Large AI detection percentage banner
- Caution information box
- AI-generated text indicator row with count and percentage
- Professional AI detection disclaimer
"""
import os
import pymupdf

class AIOverviewGenerator:
    """Generates Section 2 AI Writing Overview dashboard page."""

    @staticmethod
    def generate_overview_page(criteria: dict, ai_report) -> pymupdf.Document:
        """
        Creates a Letter-sized PDF page for the AI Writing Overview.
        """
        doc = pymupdf.open()
        page = doc.new_page(width=612.0, height=792.0)

        turnitin_logo_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'static', 'images', 'turnitin', 'turnitin_logo_exact.png'
        )
        ai_star_icon = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'static', 'images', 'turnitin', 'ai_indicator_star.png'
        )

        sub_id = criteria.get('submission_id', 'trn:oid:::8971:157249595')
        total_pages = criteria.get('total_pages', 17)

        # 1. Running Header
        if os.path.exists(turnitin_logo_path):
            page.insert_image(pymupdf.Rect(36.0, 24.0, 91.0, 40.5), filename=turnitin_logo_path)
        page.insert_text(pymupdf.Point(107.0, 34.0), f"Page 2 of {total_pages} - AI Writing Overview", fontname="helv", fontsize=6.0, color=(0.1, 0.1, 0.1))
        page.insert_text(pymupdf.Point(460.67, 34.0), "Submission ID", fontname="helv", fontsize=6.0, color=(0.1, 0.1, 0.1))
        page.insert_text(pymupdf.Point(506.12, 34.0), sub_id, fontname="helv", fontsize=6.0, color=(0.1, 0.1, 0.1))

        # Thin divider below header
        shape = page.new_shape()
        shape.draw_line(pymupdf.Point(36.0, 60.0), pymupdf.Point(576.0, 60.0))
        shape.finish(color=(0.8, 0.8, 0.8), width=0.5)
        shape.commit()

        # 2. Left side: Percentage & Explanation
        ai_pct = int(round(getattr(ai_report, 'overall_ai_score', 0.0)))
        page.insert_text(pymupdf.Point(36.0, 98.0), f"{ai_pct}% detected as AI", fontname="helv", fontsize=17.0, color=(0.1, 0.1, 0.1))

        exp_lines = [
            "The percentage indicates the combined amount of likely AI-generated text as",
            "well as likely AI-generated text that was also likely revised by AI."
        ]
        page.insert_text(pymupdf.Point(36.0, 108.0), exp_lines[0], fontname="helv", fontsize=7.0, color=(0.3, 0.3, 0.3))
        page.insert_text(pymupdf.Point(36.0, 118.0), exp_lines[1], fontname="helv", fontsize=7.0, color=(0.3, 0.3, 0.3))

        # 3. Right side: Caution Box (x=306, y=76, w=273, h=56)
        caution_rect = pymupdf.Rect(306.0, 76.0, 579.0, 132.0)
        shape = page.new_shape()
        shape.draw_rect(caution_rect)
        shape.finish(fill=(0.816, 0.910, 0.976), color=None) # #d0e8f9 light cyan-blue
        shape.commit()

        page.insert_text(pymupdf.Point(318.0, 92.0), "Caution: Review required.", fontname="helv", fontsize=6.0, color=(0.1, 0.1, 0.1))
        c_lines = [
            "It is essential to understand the limitations of AI detection before making decisions",
            "about a student's work. We encourage you to learn more about our AI detection",
            "capabilities before using the tool."
        ]
        page.insert_text(pymupdf.Point(318.0, 107.0), c_lines[0], fontname="helv", fontsize=6.0, color=(0.2, 0.2, 0.2))
        page.insert_text(pymupdf.Point(318.0, 115.0), c_lines[1], fontname="helv", fontsize=6.0, color=(0.2, 0.2, 0.2))
        page.insert_text(pymupdf.Point(318.0, 123.0), c_lines[2], fontname="helv", fontsize=6.0, color=(0.2, 0.2, 0.2))

        # Divider at y=148
        shape = page.new_shape()
        shape.draw_line(pymupdf.Point(36.0, 148.0), pymupdf.Point(576.0, 148.0))
        shape.finish(color=(0.8, 0.8, 0.8), width=0.5)
        shape.commit()

        # 4. Middle Section: AI-Generated Indicator Row
        if os.path.exists(ai_star_icon):
            page.insert_image(pymupdf.Rect(36.0, 168.0, 48.0, 180.0), filename=ai_star_icon)

        ai_count = getattr(ai_report, 'ai_sentence_count', 0)
        indicator_text = f"{ai_count}  AI-generated {ai_pct}%"
        page.insert_text(pymupdf.Point(52.0, 174.0), indicator_text, fontname="helv", fontsize=7.0, color=(0.1, 0.1, 0.1))
        page.insert_text(
            pymupdf.Point(52.0, 184.0),
            "Likely generated or likely generated and revised by AI.",
            fontname="helv",
            fontsize=7.0,
            color=(0.3, 0.3, 0.3)
        )

        # Divider at y=200
        shape = page.new_shape()
        shape.draw_line(pymupdf.Point(36.0, 200.0), pymupdf.Point(576.0, 200.0))
        shape.finish(color=(0.8, 0.8, 0.8), width=0.5)
        shape.commit()

        # 5. Bottom Section: Disclaimer
        page.insert_text(pymupdf.Point(36.0, 224.0), "Disclaimer", fontname="helv", fontsize=6.0, color=(0.1, 0.1, 0.1))
        disc_lines = [
            "Our AI writing assessment is designed to help educators identify text that might be prepared by a generative AI tool. Our AI writing assessment may not always be accurate (it may misidentify",
            "writing that is likely human generated as AI generated and likely AI generated as human generated) so it should not be used as the sole basis for adverse actions against a student. It takes",
            "further scrutiny and human judgment in conjunction with an organization's application of its specific academic policies to determine whether any academic misconduct has occurred."
        ]
        page.insert_text(pymupdf.Point(36.0, 232.0), disc_lines[0], fontname="helv", fontsize=6.0, color=(0.3, 0.3, 0.3))
        page.insert_text(pymupdf.Point(36.0, 240.0), disc_lines[1], fontname="helv", fontsize=6.0, color=(0.3, 0.3, 0.3))
        page.insert_text(pymupdf.Point(36.0, 248.0), disc_lines[2], fontname="helv", fontsize=6.0, color=(0.3, 0.3, 0.3))

        # Divider at y=264
        shape = page.new_shape()
        shape.draw_line(pymupdf.Point(36.0, 264.0), pymupdf.Point(576.0, 264.0))
        shape.finish(color=(0.8, 0.8, 0.8), width=0.5)
        shape.commit()

        # 6. Running Footer
        if os.path.exists(turnitin_logo_path):
            page.insert_image(pymupdf.Rect(36.0, 748.0, 91.0, 764.5), filename=turnitin_logo_path)
        page.insert_text(pymupdf.Point(107.0, 757.5), f"Page 2 of {total_pages} - AI Writing Overview", fontname="helv", fontsize=6.0, color=(0.1, 0.1, 0.1))
        page.insert_text(pymupdf.Point(460.67, 757.5), "Submission ID", fontname="helv", fontsize=6.0, color=(0.1, 0.1, 0.1))
        page.insert_text(pymupdf.Point(506.12, 757.5), sub_id, fontname="helv", fontsize=6.0, color=(0.1, 0.1, 0.1))

        return doc
