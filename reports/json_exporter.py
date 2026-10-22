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
        },
        'exclusion_settings': report.exclusion_settings,
        'sources_checked': report.sources_checked,
        'matched_passages': passages,
        'limitations': report.limitations,
        'export_timestamp': datetime.now().isoformat(),
    }

    return data
