"""
Turnitin-Style Report Generator & Metrics Formatter.
===================================================
Produces the structured JSON payload exactly conforming to industrial specifications:
- submission_details
- integrity_overview
- top_sources
- annotated_document_spans
"""

from __future__ import annotations
import math
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set
from .ingestion import ParsedDocument
from .top_sources import TopSourceItem, AnnotatedDocumentSpan
from .exclusions import ExclusionFiltersEngine


class PlagiarismReportGenerator:
    """
    Generates Turnitin-compliant structured JSON report payloads.
    Guarantees mathematical integrity across source breakdowns and match groups.
    """

    @classmethod
    def build_report(
        cls,
        parsed_doc: ParsedDocument,
        top_sources: List[TopSourceItem],
        annotated_spans: List[AnnotatedDocumentSpan],
        claimed_tokens: Set[int],
        exclusion_engine: ExclusionFiltersEngine,
        submission_id: Optional[str] = None,
        submission_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Assembles complete plagiarism detection report dictionary matching Turnitin schema.
        """
        total_words = max(1, parsed_doc.word_count)
        total_matched_words = len(claimed_tokens)

        # 1. Overall Similarity Percentage
        overall_sim_float = (total_matched_words / total_words) * 100.0
        overall_sim_int = int(round(overall_sim_float))
        if overall_sim_float > 0 and overall_sim_int == 0:
            # If match exists but rounds to 0, Turnitin displays minimum or integer representation
            overall_sim_int = 1 if overall_sim_float >= 0.5 else 0

        # 2. Database Breakdown (Internet, Publications, Submitted works)
        internet_words = 0
        publications_words = 0
        submitted_works_words = 0

        for s in top_sources:
            stype = (s.source_type or "").lower()
            if "submit" in stype or "student" in stype:
                submitted_works_words += s.matched_word_count
            elif "pub" in stype or "journal" in stype or "academic" in stype:
                publications_words += s.matched_word_count
            else:
                internet_words += s.matched_word_count

        total_db_words = internet_words + publications_words + submitted_works_words
        if overall_sim_int > 0 and total_db_words > 0:
            int_pct = int(round(overall_sim_int * (internet_words / total_db_words)))
            pub_pct = int(round(overall_sim_int * (publications_words / total_db_words)))
            sub_pct = int(round(overall_sim_int * (submitted_works_words / total_db_words)))
            # Adjust rounding difference so sum equals overall_sim_int
            diff = overall_sim_int - (int_pct + pub_pct + sub_pct)
            if diff != 0:
                if internet_words >= publications_words and internet_words >= submitted_works_words:
                    int_pct = max(0, int_pct + diff)
                elif publications_words >= submitted_works_words:
                    pub_pct = max(0, pub_pct + diff)
                else:
                    sub_pct = max(0, sub_pct + diff)
        else:
            int_pct, pub_pct, sub_pct = 0, 0, 0

        # 3. Match Groups Breakdown
        # Count words per classification from annotated spans
        group_words = {
            "not_cited_or_quoted": 0,
            "missing_quotations": 0,
            "missing_citation": 0,
            "cited_and_quoted": 0,
        }

        for span in annotated_spans:
            w_count = len(span.text_snippet.split())
            cls_name = span.classification
            if cls_name in group_words:
                group_words[cls_name] += w_count
            else:
                group_words["not_cited_or_quoted"] += w_count

        total_grp_words = sum(group_words.values())
        if overall_sim_int > 0 and total_grp_words > 0:
            nc_pct = int(round(overall_sim_int * (group_words["not_cited_or_quoted"] / total_grp_words)))
            mq_pct = int(round(overall_sim_int * (group_words["missing_quotations"] / total_grp_words)))
            mc_pct = int(round(overall_sim_int * (group_words["missing_citation"] / total_grp_words)))
            cq_pct = int(round(overall_sim_int * (group_words["cited_and_quoted"] / total_grp_words)))

            # Adjust rounding difference
            diff = overall_sim_int - (nc_pct + mq_pct + mc_pct + cq_pct)
            if diff != 0:
                nc_pct = max(0, nc_pct + diff)
        else:
            nc_pct, mq_pct, mc_pct, cq_pct = 0, 0, 0, 0

        # 4. Formatted Submission Details
        sub_id = submission_id or parsed_doc.document_id
        if not sub_id.startswith("trn:oid:::"):
            sub_id = f"trn:oid:::3971:{sub_id}"

        sub_date = submission_date or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # 5. Top Sources List Payload
        top_sources_payload = [s.to_dict() for s in top_sources]

        # 6. Annotated Spans Payload
        annotated_spans_payload = [span.to_dict() for span in annotated_spans]

        return {
            "submission_details": {
                "submission_id": sub_id,
                "filename": parsed_doc.filename,
                "submission_date": sub_date,
                "word_count": parsed_doc.word_count,
                "char_count": parsed_doc.char_count,
                "page_count": parsed_doc.page_count,
                "language_detected": parsed_doc.language_detected,
            },
            "integrity_overview": {
                "overall_similarity_percent": overall_sim_int,
                "source_breakdown": {
                    "internet_percent": int_pct,
                    "publications_percent": pub_pct,
                    "submitted_works_percent": sub_pct,
                },
                "filters_applied": {
                    "bibliography_excluded": exclusion_engine.exclude_bibliography,
                    "quotes_excluded": exclusion_engine.exclude_quotations,
                    "citations_excluded": exclusion_engine.exclude_citations,
                },
                "match_groups": {
                    "not_cited_or_quoted_percent": nc_pct,
                    "missing_quotations_percent": mq_pct,
                    "missing_citation_percent": mc_pct,
                    "cited_and_quoted_percent": cq_pct,
                },
            },
            "top_sources": top_sources_payload,
            "annotated_document_spans": annotated_spans_payload,
        }
