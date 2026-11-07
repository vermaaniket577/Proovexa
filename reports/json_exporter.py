import re
"""
JSON report exporter for integration with other systems.
"""
import json
from datetime import datetime


def generate_json_report(report):
    """
    Generate a JSON export of the similarity report.
    
    Args:
        report: SimilarityReport model instance
    
    Returns:
        dict containing the full report data
    """
    matches = report.matched_passages.select_related('source').order_by(
        'submitted_page', 'submitted_char_start'
    )

    passages = []
    for match in matches:
        passages.append({
            'id': match.id,
            'match_type': match.match_type,
            'match_type_display': match.get_match_type_display(),
            'similarity_score': match.similarity_score,
            'word_count': match.word_count,
            'submitted_text': match.submitted_text,
            'submitted_page': match.submitted_page,
            'submitted_paragraph': match.submitted_paragraph,
            'submitted_char_start': match.submitted_char_start,
            'submitted_char_end': match.submitted_char_end,
            'source': {
                'id': str(match.source.id) if match.source else None,
                'title': match.source.title if match.source else None,
                'type': match.source.get_source_type_display() if match.source else None,
                'url': match.source.url if match.source else None,
                'doi': match.source.doi if match.source else None,
            } if match.source else None,
            'source_text': match.source_text,
            'source_page': match.source_page,
            'source_paragraph': match.source_paragraph,
            'source_index': match.source_index,
            'color_code': match.color_code,
            'is_excluded': match.is_excluded,
            'exclusion_reason': match.exclusion_reason,
        })

    data = {
        'report': {
            'id': str(report.id),
            'status': report.status,
            'created_at': report.created_at.isoformat(),
            'engine_version': report.engine_version,
            'processing_time_seconds': report.processing_time_seconds,
        },
        'document': {
            'id': str(report.document.id),
            'title': report.document.title,
            'file_type': report.document.file_type,
            'author': report.document.uploaded_by.get_full_name() if report.document.uploaded_by else None,
            'upload_date': report.document.uploaded_at.isoformat(),
            'word_count': report.document.word_count,
            'page_count': report.document.page_count,
        },
        'results': {
            'overall_similarity': report.overall_similarity,
            'total_words': report.total_words,
            'matched_words': report.matched_words,
            'source_count': report.source_count,
            'exact_match_count': report.exact_match_count,
            'phrase_match_count': report.phrase_match_count,
            'fuzzy_match_count': report.fuzzy_match_count,
            'source_breakdown': report.source_breakdown,
        },
        'exclusion_settings': report.exclusion_settings,
        'sources_checked': report.sources_checked,
        'matched_passages': passages,
        'limitations': report.limitations,
        'export_timestamp': datetime.now().isoformat(),
    }

    return data


def generate_turnitin_schema_json(report):
    """
    Generate Turnitin-compliant structured JSON report payload.
    
    Args:
        report: SimilarityReport model instance
        
    Returns:
        dict matching the Turnitin schema with submission_details,
        integrity_overview, top_sources, and annotated_document_spans.
    """
    from reports.criteria import compute_report_criteria
    from analysis.plagiarism_engine.exclusions import ExclusionFiltersEngine

    criteria = compute_report_criteria(report)
    doc = report.document
    excl = report.exclusion_settings or {}

    # 1. Submission Details
    sub_details = {
        "submission_id": criteria.get("submission_id", f"trn:oid:::3971:{report.id.hex[:9]}"),
        "filename": doc.original_filename or doc.title or "submission.docx",
        "submission_date": report.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "word_count": report.total_words or doc.word_count or 1,
        "char_count": criteria.get("char_count", (report.total_words or 1) * 6),
        "page_count": doc.page_count or 1,
        "language_detected": criteria.get("language_detected", "en-IN"),
    }

    # 2. Database breakdown percentages
    db_sources = criteria.get("database_sources", [])
    int_pct = 0
    pub_pct = 0
    sub_pct = 0
    for db in db_sources:
        name = db.get("name", "").lower()
        val = int(re.sub(r'[^\d]', '', db.get("percent", "0")) or 0)
        if "internet" in name:
            int_pct = val
        elif "pub" in name:
            pub_pct = val
        elif "submit" in name or "student" in name:
            sub_pct = val

    # 3. Match groups breakdown percentages
    match_groups = criteria.get("match_groups", [])
    nc_pct = 0
    mq_pct = 0
    mc_pct = 0
    cq_pct = 0
    for mg in match_groups:
        mname = mg.get("name", "").lower()
        val = int(re.sub(r'[^\d]', '', mg.get("percent", "0")) or 0)
        if "not cited" in mname:
            nc_pct = val
        elif "missing quot" in mname:
            mq_pct = val
        elif "missing cit" in mname:
            mc_pct = val
        elif "cited and" in mname:
            cq_pct = val

    overall_pct = int(round(report.overall_similarity))

    integrity_overview = {
        "overall_similarity_percent": overall_pct,
        "source_breakdown": {
            "internet_percent": int_pct,
            "publications_percent": pub_pct,
            "submitted_works_percent": sub_pct,
        },
        "filters_applied": {
            "bibliography_excluded": excl.get("exclude_bibliography", True),
            "quotes_excluded": excl.get("exclude_quotations", True),
            "citations_excluded": excl.get("exclude_citations", True),
        },
        "match_groups": {
            "not_cited_or_quoted_percent": nc_pct,
            "missing_quotations_percent": mq_pct,
            "missing_citation_percent": mc_pct,
            "cited_and_quoted_percent": cq_pct,
        },
    }

    # 4. Top Sources
    top_sources = []
    raw_sources = criteria.get("top_sources", [])
    for rank, s in enumerate(raw_sources, 1):
        pct_display = s.get("pct_display") or s.get("percent_display") or f"{s.get('percentage', 0)}%"
        if "<1%" in str(pct_display) or s.get("percentage", 0) < 1.0:
            sim_pct = "<1%"
        else:
            sim_pct = int(round(s.get("percentage", 1)))

        top_sources.append({
            "rank": rank,
            "source_id": f"src_{rank:03d}",
            "source_name": s.get("clean_title") or s.get("title") or f"Source #{rank}",
            "source_type": s.get("category") or "Internet",
            "similarity_percent": sim_pct,
            "matched_word_count": s.get("unique_matched_words") or s.get("words", 0),
        })

    # 5. Annotated Document Spans
    passages = report.matched_passages.filter(is_excluded=False).order_by("submitted_page", "submitted_char_start")
    annotated_spans = []
    ex_engine = ExclusionFiltersEngine()

    for idx, p in enumerate(passages, 1):
        snippet = (p.submitted_text or "").strip()
        classification = ex_engine.classify_match_span(
            p.submitted_char_start,
            p.submitted_char_end,
            p.report.document.title + " " + snippet
        )
        annotated_spans.append({
            "span_id": idx,
            "source_rank": p.source_index or 1,
            "start_char": p.submitted_char_start,
            "end_char": p.submitted_char_end,
            "text_snippet": snippet[:180] + ("..." if len(snippet) > 180 else ""),
            "source_url": getattr(p.source, "url", "") if p.source else "",
            "classification": classification,
        })

    return {
        "submission_details": sub_details,
        "integrity_overview": integrity_overview,
        "top_sources": top_sources,
        "annotated_document_spans": annotated_spans,
    }

