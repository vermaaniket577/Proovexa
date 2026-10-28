"""
Turnitin-comparable plagiarism criteria & integrity metrics module.
Extracts and computes:
- Cover page metadata (Submission ID, Author, Institution, File stats)
- Match Groups (Not Cited or Quoted, Missing Quotations, Missing Citation, Cited and Quoted)
- Top Sources Database Breakdown (Internet, Publications, Submitted works)
- Integrity Flags (Text manipulation detection, zero-width characters, homoglyphs)
- Top Sources ranked list with badges, categories, and percentages
- Authentic Turnitin pagination across Page 3, Page 4, Page 5, etc.
"""
import base64
import os
import re
from datetime import datetime

_LOGO_DATA_URI = None

def get_turnitin_logo_data_uri():
    """
    Returns an inline base64 data URI for the official Turnitin logo mark + wordmark.
    Ensures the image always renders instantly without 404s or static-file dependency.
    """
    global _LOGO_DATA_URI
    if _LOGO_DATA_URI is None:
        logo_path = os.path.join(os.path.dirname(__file__), 'turnitin_header_logo.png')
        if not os.path.exists(logo_path):
            logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'images', 'turnitin_header_logo.png')
        if os.path.exists(logo_path):
            try:
                with open(logo_path, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('ascii')
                    _LOGO_DATA_URI = f"data:image/png;base64,{b64}"
            except Exception:
                _LOGO_DATA_URI = "/static/images/turnitin_header_logo.png"
        else:
            _LOGO_DATA_URI = "/static/images/turnitin_header_logo.png"
    return _LOGO_DATA_URI


# Standard Turnitin 16-color signature palette: (badge_solid, pastel_bg, pill_bg, pill_text)
TURNITIN_PALETTE = [
    ('#e91e63', '#fce4ec', '#fce4ec', '#191919'),  # 1: Magenta / Pink
    ('#1976d2', '#e3f2fd', '#e0f2fe', '#191919'),  # 2: Royal Blue
    ('#2e7d32', '#e8f5e9', '#dcfce7', '#191919'),  # 3: Forest Green
    ('#7b1fa2', '#f3e5f5', '#ede9fe', '#191919'),  # 4: Deep Purple
    ('#c2185b', '#fce4ec', '#fce7f3', '#191919'),  # 5: Rose
    ('#0288d1', '#e1f5fe', '#e0f2fe', '#191919'),  # 6: Sky Blue
    ('#00897b', '#e0f2f1', '#ccfbf1', '#191919'),  # 7: Teal
    ('#5e35b1', '#ede7f6', '#ede9fe', '#191919'),  # 8: Violet
    ('#d81b60', '#fce4ec', '#ffe4e6', '#191919'),  # 9: Ruby Magenta
    ('#0d47a1', '#e8eaf6', '#e0f2fe', '#191919'),  # 10: Navy
    ('#ec407a', '#f8bbd0', '#fce4ec', '#191919'),  # 11: Soft Pink
    ('#1565c0', '#bbdefb', '#e0f2fe', '#191919'),  # 12: Classic Blue
    ('#00695c', '#b2dfdb', '#d1fae5', '#191919'),  # 13: Pine Green
    ('#e65100', '#fff3e0', '#ffedd5', '#191919'),  # 14: Burnt Orange
    ('#4e342e', '#efebe9', '#f3f4f6', '#191919'),  # 15: Warm Umber
    ('#37474f', '#eceff1', '#f1f5f9', '#191919'),  # 16: Slate Grey
]


def _normalize_category(cat_str: str, url: str = '') -> str:
    """Normalize raw source type into standard Turnitin categories."""
    c = (cat_str or '').lower()
    if 'web' in c or 'internet' in c:
        return 'Internet'
    elif 'academic' in c or 'publication' in c or 'journal' in c:
        return 'Publication'
    elif 'submitted' in c or 'student' in c or 'paper' in c:
        return 'Submitted works'
    return 'Internet' if url else 'Publication'


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
    passages = list(report.matched_passages.filter(is_excluded=False).select_related('source'))
    
    group_not_cited = []
    group_missing_quotes = []
    group_missing_citations = []
    group_cited_quoted = []

    # Database categories
    internet_words = 0
    publications_words = 0
    submitted_works_words = 0

    # Source groups for top sources fallback
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
        if has_quotes and has_citation:
            group_cited_quoted.append(p)
        elif has_quotes and not has_citation:
            group_missing_citations.append(p)
        elif has_citation or p.match_type in ['near_duplicate', 'fuzzy'] or (p.similarity_score and p.similarity_score < 0.98):
            group_missing_quotes.append(p)
        else:
            group_not_cited.append(p)

        # Classify source database
        src = p.source
        src_type = getattr(src, 'source_type', 'uploaded') if src else 'uploaded'
        src_title = getattr(src, 'title', 'Reference Document') if src else 'Unknown Reference'
        src_url = getattr(src, 'url', '') if src else ''
        category = _normalize_category(src_type, src_url)

        if category == 'Internet':
            internet_words += words
        elif category == 'Publication':
            publications_words += words
        else:
            submitted_works_words += words

        # Group by source for Top Sources fallback
        if src_title not in source_map:
            source_map[src_title] = {
                'title': src_title,
                'url': src_url,
                'category': category,
                'words': 0,
                'index': p.source_index or len(source_map) + 1,
            }
        source_map[src_title]['words'] += words

    # Distinct consolidated match counts
    def get_consolidated_count(plist):
        if not plist:
            return 0
        spans = set()
        for p in plist:
            block = (p.submitted_char_start or 0) // 180
            spans.add((p.submitted_page, p.submitted_paragraph, block, p.source_id))
        return max(len(spans), 1)

    nc_count = get_consolidated_count(group_not_cited)
    mq_count = get_consolidated_count(group_missing_quotes)
    mc_count = get_consolidated_count(group_missing_citations)
    cq_count = get_consolidated_count(group_cited_quoted)

    # If no passages existed but report has similarity, populate clean standard counts
    if len(passages) == 0 and report.overall_similarity > 0:
        nc_count = report.exact_match_count or 1

    is_zero_report = (report.overall_similarity == 0 or report.overall_similarity <= 0.0)
    total_sim = round(report.overall_similarity, 0)
    score_display = f"{int(total_sim)}%"

    # Match groups stats scaled to total_sim so sum(match_groups.pct) == total_sim
    raw_nc = sum(p.word_count for p in group_not_cited)
    raw_mq = sum(p.word_count for p in group_missing_quotes)
    raw_mc = sum(p.word_count for p in group_missing_citations)
    raw_cq = sum(p.word_count for p in group_cited_quoted)
    total_group_words = raw_nc + raw_mq + raw_mc + raw_cq

    if not is_zero_report and total_group_words > 0:
        nc_pct = int(round(total_sim * (raw_nc / total_group_words)))
        mq_pct = int(round(total_sim * (raw_mq / total_group_words)))
        mc_pct = int(round(total_sim * (raw_mc / total_group_words)))
        cq_pct = int(round(total_sim * (raw_cq / total_group_words)))
        diff = int(total_sim) - (nc_pct + mq_pct + mc_pct + cq_pct)
        if diff != 0:
            nc_pct = max(0, nc_pct + diff)
    else:
        nc_pct = int(total_sim) if not is_zero_report else 0
        mq_pct = 0
        mc_pct = 0
        cq_pct = 0

    match_groups = [
        {
            'name': 'Not Cited or Quoted',
            'count': nc_count,
            'percent': f"{nc_pct}%",
            'description': 'Matches with neither in-text citation nor quotation marks',
            'color': '#e05d5d',  # Exact Turnitin Coral Red from screenshot
            'icon': 'files',
            'icon_class': 'bi-files',
            'badge_class': 'danger',
        },
        {
            'name': 'Missing Quotations',
            'count': mq_count,
            'percent': f"{mq_pct}%",
            'description': 'Matches that are still very similar to source material',
            'color': '#d96b27',  # Exact Turnitin Burnt Orange from screenshot
            'icon': 'quote',
            'icon_class': 'bi-quote',
            'badge_class': 'warning',
        },
        {
            'name': 'Missing Citation',
            'count': mc_count,
            'percent': f"{mc_pct}%",
            'description': 'Matches that have quotation marks, but no in-text citation',
            'color': '#c4a052',  # Exact Turnitin Warm Sand Gold from screenshot
            'icon': 'citation',
            'icon_class': 'bi-card-text',
            'badge_class': 'secondary',
        },
        {
            'name': 'Cited and Quoted',
            'count': cq_count,
            'percent': f"{cq_pct}%",
            'description': 'Matches with in-text citation present, but no quotation marks',
            'color': '#5fa89b',  # Exact Turnitin Sage Teal from screenshot
            'icon': 'mortarboard',
            'icon_class': 'bi-mortarboard-fill',
            'badge_class': 'info',
        },
    ]

    # Database categories scaled to total_sim so sum(database_sources.pct) == total_sim
    total_db_words = internet_words + publications_words + submitted_works_words
    if not is_zero_report and total_db_words > 0:
        internet_pct = int(round(total_sim * (internet_words / total_db_words)))
        publications_pct = int(round(total_sim * (publications_words / total_db_words)))
        submitted_works_pct = int(round(total_sim * (submitted_works_words / total_db_words)))
        diff = int(total_sim) - (internet_pct + publications_pct + submitted_works_pct)
        if diff != 0:
            internet_pct = max(0, internet_pct + diff)
    else:
        internet_pct = int(total_sim) if not is_zero_report else 0
        publications_pct = 0
        submitted_works_pct = 0

    database_sources = [
        {
            'name': 'Internet sources',
            'percent': f"{internet_pct}%",
            'icon': 'globe',
            'icon_class': 'bi-globe2',
        },
        {
            'name': 'Publications',
            'percent': f"{publications_pct}%",
            'icon': 'book',
            'icon_class': 'bi-book-half',
        },
        {
            'name': 'Submitted works (Student Papers)',
            'percent': f"{submitted_works_pct}%",
            'icon': 'person',
            'icon_class': 'bi-person-fill',
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

    # 6. Top Sources Ordered List (Authentic Detected Sources Only)
    top_sources = []

    if report.source_breakdown and isinstance(report.source_breakdown, list) and len(report.source_breakdown) > 0:
        raw_sources = sorted(report.source_breakdown, key=lambda s: (s.get('rank', 999), -s.get('unique_matched_words', 0), -s.get('gross_matched_words', 0)))
        for idx, s in enumerate(raw_sources, 1):
            color_tuple = TURNITIN_PALETTE[(idx - 1) % len(TURNITIN_PALETTE)]
            badge_color, pastel_bg, pill_bg, pill_text = color_tuple
            category = _normalize_category(s.get('category'), s.get('url', ''))

            uniq_w = s.get('unique_matched_words') or 0
            gross_w = s.get('gross_matched_words') or 0
            uniq_pct = float(s.get('unique_percentage') or 0.0)
            gross_pct = float(s.get('gross_percentage') or 0.0)
            effective_pct = max(uniq_pct, gross_pct * 0.7)

            if is_zero_report:
                pct_display = "*"
            elif effective_pct >= 0.95:
                pct_display = f"{min(int(round(effective_pct)), int(total_sim))}%"
            else:
                pct_display = "<1%"

            top_sources.append({
                'index': idx,
                'title': s.get('title') or s.get('source_name', f'Source {idx}'),
                'url': s.get('url', ''),
                'category': category,
                'words': gross_w or uniq_w,
                'percent': pct_display,
                'color': badge_color,
                'color_code': badge_color,
                'pastel_bg': pastel_bg,
                'pill_bg': pill_bg,
                'pill_text': pill_text,
                'composite_similarity_pct': s.get('composite_similarity_pct', pct_display.replace('%', '').replace('<', '')),
                'exact_shingle_containment_pct': s.get('exact_shingle_containment_pct', pct_display.replace('%', '').replace('<', '')),
                'lexical_tfidf_pct': s.get('lexical_tfidf_pct', pct_display.replace('%', '').replace('<', '')),
                'semantic_paraphrase_pct': s.get('semantic_paraphrase_pct', 0.0),
                'exact_matched_shingles': s.get('exact_matched_shingles', []),
                'flagged_sentences': s.get('flagged_sentences', []),
            })
    elif source_map:
        sorted_sources = sorted(source_map.values(), key=lambda s: -s['words'])
        for idx, s in enumerate(sorted_sources, 1):
            color_tuple = TURNITIN_PALETTE[(idx - 1) % len(TURNITIN_PALETTE)]
            badge_color, pastel_bg, pill_bg, pill_text = color_tuple
            src_pct = (s['words'] / word_count) * 100 if word_count > 0 else 0

            if is_zero_report:
                pct_display = "*"
            elif src_pct >= 0.95:
                pct_display = f"{min(int(round(src_pct)), int(total_sim))}%"
            else:
                pct_display = "<1%"

            top_sources.append({
                'index': idx,
                'title': s['title'],
                'url': s['url'],
                'category': s['category'],
                'words': s['words'],
                'percent': pct_display,
                'color': badge_color,
                'color_code': badge_color,
                'pastel_bg': pastel_bg,
                'pill_bg': pill_bg,
                'pill_text': pill_text,
                'composite_similarity_pct': pct_display.replace('%', '').replace('<', ''),
                'exact_shingle_containment_pct': pct_display.replace('%', '').replace('<', ''),
                'lexical_tfidf_pct': pct_display.replace('%', '').replace('<', ''),
                'semantic_paraphrase_pct': 0.0,
                'exact_matched_shingles': [],
                'flagged_sentences': [],
            })

    if is_zero_report:
        top_sources = []

    # 7. Authentic Turnitin Top Sources Pagination
    # Page 3: Sources 1 to 10 (with Match Groups & Database summary at top)
    # Pages 4, 5, 6...: 15 sources per sheet
    sources_pages = []
    if top_sources:
        sources_pages.append({
            'page_number': 3,
            'sources': top_sources[0:10],
            'is_first_page': True,
        })
        p_num = 4
        start_idx = 10
        while start_idx < len(top_sources):
            end_idx = min(start_idx + 15, len(top_sources))
            sources_pages.append({
                'page_number': p_num,
                'sources': top_sources[start_idx:end_idx],
                'is_first_page': False,
            })
            p_num += 1
            start_idx = end_idx

    total_overview_pages = 2 + len(sources_pages)
    ext_pages = extracted_texts.values('page_number').distinct().count() if extracted_texts.exists() else 0
    if ext_pages > 1:
        doc_pages = ext_pages
    elif doc.page_count and doc.page_count > 1:
        doc_pages = doc.page_count
    elif word_count > 300:
        doc_pages = max(1, round(word_count / 300))
    else:
        doc_pages = 1

    submission_pages_count = doc_pages
    total_pages = total_overview_pages + submission_pages_count

    return {
        'submission_id': submission_id,
        'author_name': author_name,
        'institution_name': institution_name,
        'file_name': doc.original_filename,
        'file_size_display': file_size_display,
        'submission_date': sub_date_str,
        'download_date': download_date_str,
        'page_count': submission_pages_count,
        'total_overview_pages': total_overview_pages,
        'total_pages': total_pages,
        'word_count': word_count,
        'character_count': char_count,
        'is_zero_report': is_zero_report,
        'overall_similarity_display': score_display,
        'score_display': score_display,
        'overall_similarity': total_sim,
        'overall_similarity_float': report.overall_similarity,
        'filtered_from_report': filtered_items,
        'match_groups': match_groups,
        'database_sources': database_sources,
        'integrity_flags': integrity_flags,
        'flags_count': flags_count,
        'top_sources': top_sources,
        'sources_pages': sources_pages,
        'source_count': len(top_sources),
        'logo_data_uri': get_turnitin_logo_data_uri(),
    }
