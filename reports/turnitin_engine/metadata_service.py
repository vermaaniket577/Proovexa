"""
Metadata service for Turnitin-style reports.
Extracts and normalizes document metadata, statistics, exclusion criteria,
integrity flags, and source palettes.
"""
from typing import Dict, Any, List
from reports.criteria import compute_report_criteria, TURNITIN_PALETTE

class ReportMetadataService:
    """Provides structured metadata for Turnitin report generators."""

    @staticmethod
    def get_metadata(report) -> Dict[str, Any]:
        """
        Compute standard criteria and enrich with presentation metadata.
        """
        criteria = compute_report_criteria(report)
        return criteria

    @staticmethod
    def get_source_color(source_index: int) -> tuple:
        """
        Returns (badge_color_hex, pastel_bg_hex, pill_bg_hex, pill_text_hex)
        """
        idx = max(1, source_index)
        return TURNITIN_PALETTE[(idx - 1) % len(TURNITIN_PALETTE)]
