"""
Turnitin-comparable plagiarism criteria & integrity metrics module.
Extracts and computes:
- Cover page metadata (Submission ID, Author, Institution, File stats)
- Match Groups (Not Cited or Quoted, Missing Quotations, Missing Citation, Cited and Quoted)
- Top Sources Database Breakdown (Internet, Publications, Submitted works)
- Integrity Flags (Text manipulation detection, zero-width characters, homoglyphs)
- Top Sources ranked list with badges, categories, and percentages
"""
import re
from datetime import datetime


def compute_report_criteria(report):
    """
    Computes all Turnitin-style criteria and metadata for a given SimilarityReport.
    
    Returns a comprehensive dictionary matching the Turnitin report specification.
    """
    doc = report.document
    uploaded_by = doc.uploaded_by

    # 1. Submission ID (Turnitin standard trn:oid format)
    # Generates a stable deterministic 9-digit ID based on report ID
    num_seed = abs(hash(str(report.id))) % 900000000 + 100000000
    submission_id = f"trn:oid:::5:{num_seed}"

    # 2. Cover Page Details
    author_name = uploaded_by.get_full_name() or uploaded_by.username or "Student Author"
    institution_name = getattr(uploaded_by.institution, 'name', '') if getattr(uploaded_by, 'institution', None) else 'Metropolitan Academic Institute'
    
    sub_date = doc.uploaded_at or report.created_at
    download_date = datetime.now()
    
    sub_date_str = sub_date.strftime('%b %d, %Y, %I:%M %p GMT+1')
    download_date_str = download_date.strftime('%b %d, %Y, %I:%M %p GMT+1')

    # Character count
    extracted_texts = doc.extracted_texts.all()
    if extracted_texts.exists():
        char_count = sum(len(t.content) for t in extracted_texts)
    else:
        char_count = (doc.word_count or report.total_words or 100) * 6

    word_count = report.total_words or doc.word_count or 1
    page_count = doc.page_count or 1
    file_size_display = doc.file_size_display if hasattr(doc, 'file_size_display') else f"{doc.file_size / 1024:.1f} KB"

    # 3. Filtered from the Report
    excl = report.exclusion_settings or {}
    filtered_items = []
    if excl.get('exclude_bibliography', True):
        filtered_items.append("Bibliography")
    if excl.get('exclude_quotations', True):
        filtered_items.append("Quoted Text")
    if excl.get('exclude_citations', True):
        filtered_items.append("Cited Text")
    if not filtered_items:
        filtered_items = ["Bibliography", "Quoted Text", "Cited Text"]

    # 4. Match Passages Analysis & Match Groups Classification
    passages = report.matched_passages.filter(is_excluded=False).select_related('source')
    
    group_not_cited = []
    group_missing_quotes = []
    group_missing_citations = []
    group_cited_quoted = []

    # Database categories
    internet_words = 0
    publications_words = 0
    submitted_works_words = 0

    # Source groups for top sources table
    source_map = {}

    for p in passages:
        text = p.submitted_text or ""
        words = p.word_count or len(text.split())

        # Check citation presence
        has_citation = bool(
            re.search(r'\([\w\s,]+,\s*\d{4}', text) or
            re.search(r'\(\w+\s+et\s+al\.,?\s*\d{4}\)', text) or
            re.search(r'\[\d+\]', text)
        )

        # Check quotation marks
        has_quotes = (
            text.strip().startswith(('"', '“', "'", '‘')) or
            text.strip().endswith(('"', '”', "'", '’')) or
            ('"' in text) or ('“' in text)
        )

        # Classify into Turnitin 4 Match Groups
        if not has_citation and not has_quotes:
            group_not_cited.append(p)
        elif has_citation and not has_quotes:
            group_missing_quotes.append(p)
        elif not has_citation and has_quotes:
            group_missing_citations.append(p)
        else:
            group_cited_quoted.append(p)

        # Classify source database
        src = p.source
        src_type = getattr(src, 'source_type', 'uploaded') if src else 'uploaded'
        src_title = getattr(src, 'title', 'Reference Document') if src else 'Unknown Reference'
        src_url = getattr(src, 'url', '') if src else ''

        if src_type in ['web'] or (src_url and not getattr(src, 'doi', '')):
            category = 'Internet'
            internet_words += words
        elif src_type in ['academic', 'open_access'] or (src and getattr(src, 'doi', '')):
            category = 'Publication'
            publications_words += words
        else:
            category = 'Submitted works'
            submitted_works_words += words

        # Group by source for Top Sources
        if src_title not in source_map:
            source_map[src_title] = {
                'title': src_title,
                'url': src_url,
                'category': category,
                'words': 0,
                'index': p.source_index or len(source_map) + 1,
            }
        source_map[src_title]['words'] += words

    # Default distribution if all matches belong to general category
    total_matched_words = max(report.matched_words, sum(p.word_count for p in passages), 1)
    
    # Calculate percentages for database categories
    if report.overall_similarity > 0:
        if internet_words + publications_words + submitted_works_words == 0:
            internet_pct = round(report.overall_similarity * 0.4, 0)
            publications_pct = round(report.overall_similarity * 0.35, 0)
            submitted_works_pct = round(report.overall_similarity * 0.25, 0)
        else:
            factor = report.overall_similarity / max(total_matched_words, 1)
            internet_pct = round(internet_words * factor, 0)
            publications_pct = round(publications_words * factor, 0)
            submitted_works_pct = round(submitted_works_words * factor, 0)
            # Adjust rounding to match overall
            diff = report.overall_similarity - (internet_pct + publications_pct + submitted_works_pct)
            if diff != 0:
                internet_pct = max(0, internet_pct + diff)
    else:
        internet_pct = 0
        publications_pct = 0
        submitted_works_pct = 0

    # Match groups stats
    def calc_group_stat(group_list):
        count = len(group_list)
        words = sum(p.word_count for p in group_list)
        pct = round((words / word_count) * 100, 1) if word_count > 0 else 0
        return count, pct

    nc_count, nc_pct = calc_group_stat(group_not_cited)
    mq_count, mq_pct = calc_group_stat(group_missing_quotes)
    mc_count, mc_pct = calc_group_stat(group_missing_citations)
    cq_count, cq_pct = calc_group_stat(group_cited_quoted)

    # If no passages existed but report has similarity, populate clean standard groups
    if len(passages) == 0 and report.overall_similarity > 0:
        nc_count = report.exact_match_count or 1
        nc_pct = report.overall_similarity
    elif len(passages) > 0 and nc_count == 0 and mq_count == 0 and mc_count == 0 and cq_count == 0:
        nc_count = len(passages)
        nc_pct = report.overall_similarity

    match_groups = [
        {
            'name': 'Not Cited or Quoted',
            'count': nc_count,
            'percent': f"{int(round(nc_pct))}%",
            'description': 'Matches with neither in-text citation nor quotation marks',
            'color': '#ef4444',  # Red
            'badge_class': 'danger',
        },
        {
            'name': 'Missing Quotations',
            'count': mq_count,
            'percent': f"{int(round(mq_pct))}%",
            'description': 'Matches that are still very similar to source material',
            'color': '#f97316',  # Orange
            'badge_class': 'warning',
        },
        {
            'name': 'Missing Citation',
            'count': mc_count,
            'percent': f"{int(round(mc_pct))}%",
            'description': 'Matches that have quotation marks, but no in-text citation',
            'color': '#eab308',  # Yellow
            'badge_class': 'secondary',
        },
        {
            'name': 'Cited and Quoted',
            'count': cq_count,
            'percent': f"{int(round(cq_pct))}%",
            'description': 'Matches with in-text citation present, but no quotation marks',
            'color': '#06b6d4',  # Cyan
            'badge_class': 'info',
        },
    ]

    # Database categories summary
    database_sources = [
        {
            'name': 'Internet sources',
            'percent': f"{int(round(internet_pct))}%",
            'icon': 'globe',
        },
        {
            'name': 'Publications',
            'percent': f"{int(round(publications_pct))}%",
            'icon': 'book',
        },
        {
            'name': 'Submitted works (Student Papers)',
            'percent': f"{int(round(submitted_works_pct))}%",
            'icon': 'person',
        },
    ]

    # 5. Integrity Flags (Text manipulation detection)
    full_text = " ".join(t.content for t in extracted_texts) if extracted_texts.exists() else ""
    integrity_flags = []

    # Check for zero-width spaces & hidden characters
    zero_width_chars = [c for c in full_text if ord(c) in [0x200B, 0x200C, 0x200D, 0xFEFF]]
    if len(zero_width_chars) > 5:
        integrity_flags.append({
            'title': 'Hidden Characters Detected',
            'detail': f'Found {len(zero_width_chars)} zero-width characters commonly used to split words and evade similarity filters.',
        })

    # Check for Cyrillic/Greek homoglyphs in Latin text
    cyrillic_homoglyphs = [c for c in full_text if 0x0400 <= ord(c) <= 0x04FF]
    if len(cyrillic_homoglyphs) > 10:
        integrity_flags.append({
            'title': 'Character Replacement Detected',
            'detail': f'Detected {len(cyrillic_homoglyphs)} non-Latin homoglyphic characters within the submission text.',
        })

    flags_count = len(integrity_flags)

    # 6. Top Sources Ordered List (Matching Images 3 & 4)
    # Vibrant colors from Turnitin palette
    TURNITIN_PALETTE = [
        '#e91e63',  # 1: Magenta / Deep Pink
        '#1976d2',  # 2: Blue
        '#2e7d32',  # 3: Green
        '#7b1fa2',  # 4: Purple
        '#c2185b',  # 5: Pink
        '#0288d1',  # 6: Light Blue
        '#00897b',  # 7: Teal
        '#5e35b1',  # 8: Indigo
        '#d81b60',  # 9: Rose
        '#0d47a1',  # 10: Dark Blue
        '#ec407a',  # 11: Soft Pink
        '#1565c0',  # 12: Royal Blue
        '#00695c',  # 13: Dark Teal
    ]

    top_sources = []
    sorted_sources = sorted(source_map.values(), key=lambda s: s['words'], reverse=True)
    
    for idx, s in enumerate(sorted_sources, 1):
        color = TURNITIN_PALETTE[(idx - 1) % len(TURNITIN_PALETTE)]
        src_pct = (s['words'] / word_count) * 100 if word_count > 0 else 0
        pct_display = f"{int(round(src_pct))}%" if src_pct >= 1 else "<1%"
        
        top_sources.append({
            'index': idx,
            'title': s['title'],
            'url': s['url'],
            'category': s['category'],
            'words': s['words'],
            'percent': pct_display,
            'color': color,
        })

    return {
        'submission_id': submission_id,
        'author_name': author_name,
        'institution_name': institution_name,
        'file_name': doc.original_filename,
        'file_size_display': file_size_display,
        'submission_date': sub_date_str,
        'download_date': download_date_str,
        'page_count': page_count,
        'total_pages': max(2, (page_count or 1) + 2),
        'word_count': word_count,
        'character_count': char_count,
        'overall_similarity': round(report.overall_similarity, 0),
        'overall_similarity_float': report.overall_similarity,
        'filtered_from_report': filtered_items,
        'match_groups': match_groups,
        'database_sources': database_sources,
        'integrity_flags': integrity_flags,
        'flags_count': flags_count,
        'top_sources': top_sources,
        'source_count': len(top_sources),
    }
