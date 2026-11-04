"""
Margin indicator badge generator.
Draws circular numbered badges in the left margin next to matched passages.
"""
import pymupdf

class MarginIndicatorGenerator:
    """Draws Turnitin margin badges next to matched text lines."""

    @staticmethod
    def draw_badge(page: pymupdf.Page, x: float, y: float, source_index: int, color_rgb: tuple):
        """
        Draws a rounded badge with source number in the left margin.
        """
        w = 17.7 if source_index < 10 else 22.0
        h = 15.5
        rect = pymupdf.Rect(x, y, x + w, y + h)

        # Background rounded badge
        shape = page.new_shape()
        shape.draw_round_rect(rect, 4.0)
        shape.finish(fill=color_rgb, color=None)
        shape.commit()

        # Source index text in bold white
        text_pt = pymupdf.Point(x + (w / 2.0) - (2.5 if source_index < 10 else 5.0), y + 10.5)
        page.insert_text(
            text_pt,
            str(source_index),
            fontname="helv",
            fontsize=7.5,
            color=(1.0, 1.0, 1.0)
        )
