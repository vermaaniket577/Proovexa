"""

Core similarity analysis engine.

Orchestrates all comparison methods, applies exclusions, and generates reports.

"""

import re

import time

import logging
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict

from django.conf import settings

from django.utils import timezone

from django.db.models import Q



from .comparators import ExactMatchComparator, NGramComparator, FuzzyComparator, TFIDFComparator

from .winnowing import WinnowingEngine

from .hybrid_checker import TurnitinStyleChecker

from .exclusions import ExclusionEngine

from .scoring import AcademicSimilarityScorer, SimilarityScorer

from .ai_api_client import AIAPIClient

from .models import SimilarityReport, MatchedPassage, ProcessingJob

from documents.models import Document, ExtractedText, ReferenceSource



logger = logging.getLogger(__name__)





class AnalysisEngine:

    """

    Main similarity analysis engine.

    

    Coordinates multiple comparison methods (Exact, Winnowing, Fuzzy, TF-IDF),

    applies exclusion rules, calculates word-level scores without double-counting,

    and persists auditable results.

    """



    def __init__(self, exclusion_settings=None, search_repositories=None, min_match_words=None):

        default_settings = {
            'exclude_bibliography': False,
            'exclude_quotations': False,
            'exclude_citations': False,
            'min_match_words': min(int(getattr(settings, 'MIN_MATCH_WORD_COUNT', 8)), 8),
            'exclude_small_matches': 8,
            'exclude_common_phrases': False,
            'common_phrases_list': [],
            'exclude_sources': [],
            'exclude_self_match': True,
            'check_web_sources': True,
            'search_repositories': ["INTERNET", "PUBLICATIONS", "SUBMITTED_WORKS"],
        }
        self.exclusion_settings = dict(default_settings)
        if exclusion_settings:
            self.exclusion_settings.update(exclusion_settings)
        if search_repositories is not None:
            self.exclusion_settings['search_repositories'] = search_repositories
        if min_match_words is not None:
            self.exclusion_settings['min_match_words'] = min_match_words

        if 'search_repositories' not in self.exclusion_settings:
            self.exclusion_settings['search_repositories'] = ["INTERNET", "PUBLICATIONS", "SUBMITTED_WORKS"]
        if 'min_match_words' in self.exclusion_settings:
            # Ensure exclude_small_matches is not set to an impossibly high value
            self.exclusion_settings['min_match_words'] = min(int(self.exclusion_settings['min_match_words']), 14)



        # Initialize comparators
        min_words = self.exclusion_settings.get('min_match_words', 8)
        self.search_repositories = self.exclusion_settings['search_repositories']
        self.min_match_words = min_words
        ngram_size = getattr(settings, 'NGRAM_SIZE', 5)



        self.winnowing_engine = WinnowingEngine(k=min_words, w=4)

        self.exact_comparator = ExactMatchComparator(min_word_count=min_words)

        self.ngram_comparator = NGramComparator(n=ngram_size)

        self.fuzzy_comparator = FuzzyComparator(threshold=0.60)

        self.tfidf_comparator = TFIDFComparator()

        self.hybrid_checker = TurnitinStyleChecker(shingle_size=min_words, semantic_threshold=0.65)

        self.ai_api_client = AIAPIClient()



        self.exclusion_engine = ExclusionEngine(self.exclusion_settings)



    def analyze_document(self, document, user=None):

        """

        Run full similarity analysis on a document.

        

        Args:

            document: Document model instance

            user: User who triggered the analysis

        

        Returns:

            SimilarityReport instance

        """

        start_time = time.time()



        # Create report

        report = SimilarityReport.objects.create(

            document=document,

            status=SimilarityReport.Status.PROCESSING,

            engine_version=getattr(settings, 'ANALYSIS_ENGINE_VERSION', '1.0.0'),

            exclusion_settings=self.exclusion_settings,

            created_by=user,

        )



        try:

            # Update document status

            document.status = Document.Status.ANALYZING

            document.save(update_fields=['status'])



            # Get full extracted text

            extracted_texts = ExtractedText.objects.filter(

                document=document

            ).order_by('page_number', 'paragraph_number')



            if not extracted_texts.exists():
                report.status = SimilarityReport.Status.FAILED
                report.error_message = "No extracted text found. Please re-upload the document."
                report.save()
                document.status = Document.Status.FAILED
                document.error_message = report.error_message
                document.save(update_fields=['status', 'error_message'])
                return report



            # Build full text and page structure

            full_text = ''

            pages = []

            current_page = None



            for et in extracted_texts:

                if current_page is None or current_page['page_number'] != et.page_number:

                    current_page = {

                        'page_number': et.page_number,

                        'paragraphs': []

                    }

                    pages.append(current_page)

                current_page['paragraphs'].append({

                    'text': et.content,

                    'para_number': et.paragraph_number,

                })

                if full_text:

                    full_text += '\n\n'

                full_text += et.content



            total_words = document.word_count or len(full_text.split())



            # Get reference sources to compare against (including Playwright live web search)

            sources = self._get_comparison_sources(document, full_text=full_text)



            if not sources:
                # Source retrieval failed and no local reference sources exist: report failure transparently!
                checked_info = getattr(self, 'last_search_meta', {}).get('sources_checked', [])
                failed_info = getattr(self, 'last_search_meta', {}).get('failed_sources', [])
                report.overall_similarity = 0.0
                report.total_words = total_words
                report.matched_words = 0
                report.source_count = 0
                report.status = SimilarityReport.Status.FAILED
                report.error_message = (
                    "Unable to complete the comparison: Could not connect to external academic "
                    "or web databases, and no local reference documents were available. "
                    "Please check network connectivity or configure API credentials."
                )
                report.processing_time_seconds = round(time.time() - start_time, 2)
                report.sources_checked = [
                    f"Sources attempted: {len(checked_info) + len(failed_info)}",
                    f"Connectors available: {', '.join(checked_info) if checked_info else 'None'}",
                ]
                report.save()

                document.status = Document.Status.FAILED
                document.error_message = report.error_message
                document.save(update_fields=['status', 'error_message'])
                return report



            # Step 1: Tokenize submitted document with offsets and compute Winnowing fingerprints

            sub_fps, sub_tokens = self.winnowing_engine.compute_fingerprints(full_text)

            total_words = len(sub_tokens) if sub_tokens else (document.word_count or len(full_text.split()))



            # Initialize academic word-position scorer

            scorer = AcademicSimilarityScorer(total_word_count=total_words, full_text=full_text)

            min_words = self.exclusion_settings.get('min_match_words', 8)

            # Detect Turnitin Integrity Flags (document manipulation detection)
            integrity_flags = []
            zero_width_chars = [c for c in full_text if ord(c) in (0x200B, 0x200C, 0x200D, 0xFEFF)]
            if len(zero_width_chars) > 5:
                integrity_flags.append({
                    'title': 'Hidden Characters Detected',
                    'subtitle': f'{len(zero_width_chars)} invisible characters detected',
                    'detail': f'Found {len(zero_width_chars)} zero-width characters used to disrupt tokenization and evade similarity matching.',
                })

            cyrillic_homoglyphs = [c for c in full_text if 0x0400 <= ord(c) <= 0x04FF]
            if len(cyrillic_homoglyphs) > 10:
                integrity_flags.append({
                    'title': 'Character Replacement Detected',
                    'subtitle': f'{len(cyrillic_homoglyphs)} suspect characters in text',
                    'detail': 'Detected non-Latin homoglyphic characters swapped with Latin letters to evade detection.',
                })



            # Detect document-level exclusion regions (e.g. bibliography sections)
            if self.exclusion_settings.get('exclude_bibliography'):
                bib_pattern = r'(?im)^\s*(?:references|bibliography|works\s+cited|reference\s+list|cited\s+literature|संदर्भ\s*सूची|ग्रंथसूची)\s*[:.]?\s*$'
                bib_matches = list(re.finditer(bib_pattern, full_text))
                valid_bib = None
                doc_len = len(full_text)
                for m in bib_matches:
                    # Only treat as bibliography if located in the latter portion (> 50% or after 2500 chars)
                    if m.start() >= doc_len * 0.50 or (doc_len > 3000 and m.start() >= 2500):
                        valid_bib = m
                        break
                if valid_bib:
                    bib_char_start = valid_bib.start()
                    bib_w_start, bib_w_end = self._char_span_to_word_span(sub_tokens, bib_char_start, len(full_text))
                    scorer.add_exclusion_span(bib_w_start, bib_w_end)



            # Step 2: TF-IDF candidate pre-filtering

            source_texts = []

            source_refs = []

            empty_source_count = 0

            for src in sources:

                text = self._get_source_text(src)

                if text and len(text.strip()) > 20:

                    source_texts.append(text)

                    source_refs.append(src)

                else:

                    empty_source_count += 1



            logger.info(

                f"Source text retrieval: {len(source_texts)} sources with text, "

                f"{empty_source_count} empty (skipped) out of {len(sources)} total"

            )



            if not source_texts:
                # Sources were found, but none yielded extractable text: report failure transparently!
                report.overall_similarity = 0.0
                report.total_words = total_words
                report.matched_words = 0
                report.source_count = 0
                report.status = SimilarityReport.Status.FAILED
                report.error_message = (
                    "Unable to complete the comparison: Reference sources were identified, but none contained "
                    "extractable text for comparison. Please verify candidate sources."
                )
                report.processing_time_seconds = round(time.time() - start_time, 2)
                report.sources_checked = [f'{len(sources)} candidate sources found, but none had extractable text']
                report.save()

                document.status = Document.Status.FAILED
                document.error_message = report.error_message
                document.save(update_fields=['status', 'error_message'])
                return report



            # Get candidate sources by TF-IDF similarity

            candidates = self.tfidf_comparator.compare_batch(full_text, source_texts)

            logger.info(f"TF-IDF pre-filter: {len(candidates)} candidate sources above threshold")



            # Limit to top candidates for detailed multi-method analysis (optimal academic recall + high speed)
            max_candidates = 15
            top_candidates = candidates[:max_candidates]

            # Ensure candidate sources with 8-to-14 word matches or title keywords are included
            sub_clean_words = re.findall(r'[\w\u0900-\u097F]+', full_text.lower())
            check_k = min(8, min_words)
            sub_k_shingles = set()
            if len(sub_clean_words) >= check_k:
                for i in range(len(sub_clean_words) - check_k + 1):
                    sub_k_shingles.add(tuple(sub_clean_words[i:i + check_k]))

            cand_indices = {c[0] for c in top_candidates}
            for s_idx, s_ref in enumerate(source_refs):
                if s_idx in cand_indices:
                    continue
                if len(top_candidates) >= 20:
                    break

                s_txt = source_texts[s_idx]

                s_title = getattr(s_ref, 'title', '').lower()



                # 1. Check title keyword overlap with document (for academic paper title matches)

                title_words = [w for w in re.findall(r'[\w\u0900-\u097F]+', s_title) if len(w) > 3]

                if title_words and sum(1 for w in title_words if w in full_text.lower()) >= min(2, len(title_words)):

                    top_candidates.append((s_idx, 0.40))

                    cand_indices.add(s_idx)

                    continue



                # 2. Check k-word shingle sequence overlap

                s_clean = re.findall(r'[\w\u0900-\u097F]+', s_txt.lower())

                if len(s_clean) >= check_k and sub_k_shingles:

                    for j in range(len(s_clean) - check_k + 1):

                        sh = tuple(s_clean[j:j + check_k])

                        if sh in sub_k_shingles:

                            top_candidates.append((s_idx, 0.70))

                            cand_indices.add(s_idx)

                            break



            all_matches = []

            source_index = 0

            sources_checked = []

            exact_count = 0

            phrase_count = 0

            fuzzy_count = 0

            winnow_count = 0



            # Pre-compute submission sentence embeddings and shingles once for rapid candidate scoring

            cached_sub_norm_tokens = self.hybrid_checker.normalize_tokens(full_text)

            cached_sub_shingles = self.hybrid_checker.get_shingles(cached_sub_norm_tokens)

            cached_sub_sents = self.hybrid_checker.split_sentences(full_text)

            cached_sub_ngrams = self.ngram_comparator._extract_ngrams(full_text)
            cached_sub_words = self.ngram_comparator._tokenize(full_text)

            cached_sub_embeddings = None



            for cand_rank, (src_idx, tfidf_score) in enumerate(top_candidates):

                if src_idx >= len(source_refs):

                    continue



                source = source_refs[src_idx]

                source_text = source_texts[src_idx]

                source_index += 1



                sources_checked.append({

                    'name': source.title,

                    'type': source.get_source_type_display(),

                    'tfidf_similarity': round(tfidf_score * 100, 2),

                })



                # Source page mapping if available

                source_pages = self._get_document_pages(source.document) if source.document else None



                # Method A: Winnowing Fingerprint Matching

                src_fps, src_tokens = self.winnowing_engine.compute_fingerprints(source_text)

                winnow_passages = self.winnowing_engine.match_fingerprints(

                    sub_fps, src_fps, full_text, source_text, min_words=min_words,

                    sub_tokens=sub_tokens, src_tokens=src_tokens

                )

                for wp in winnow_passages:

                    wp['source'] = source

                    wp['source_index'] = source_index

                    wp['match_type'] = 'exact'

                    all_matches.append(wp)

                    winnow_count += 1

                    exact_count += 1



                # Method B: Exact String Matching

                exact_result = self.exact_comparator.compare(full_text, source_text, sub_tokens=sub_tokens, src_tokens=src_tokens)

                for match in exact_result.matches:

                    match['source'] = source

                    match['source_index'] = source_index

                    match['match_type'] = 'exact'

                    all_matches.append(match)

                    exact_count += 1



                # Method C: N-Gram Phrase Matching

                ngram_result = self.ngram_comparator.compare(full_text, source_text, sub_ngrams=cached_sub_ngrams, sub_words=cached_sub_words, sub_tokens=sub_tokens)

                for match in ngram_result.matches:

                    match['source'] = source

                    match['source_index'] = source_index

                    match['match_type'] = 'phrase'

                    all_matches.append(match)

                    phrase_count += 1



                # Method D: Near-Duplicate / Fuzzy Matching (evaluate top relevant candidates)
                if cand_rank < 3 and (winnow_count > 0 or exact_count > 0 or tfidf_score > 0.12):
                    fuzzy_result = self.fuzzy_comparator.compare(full_text, source_text)
                    for match in fuzzy_result.matches:
                        match['source'] = source
                        match['source_index'] = source_index
                        match['match_type'] = 'fuzzy'
                        all_matches.append(match)
                        fuzzy_count += 1

                # Method E: Turnitin 3-Tier Hybrid Evaluation (Shingle Containment, Lexical, Semantic Paraphrase)
                shingle_containment, exact_phrases = self.hybrid_checker.compute_shingle_containment(
                    full_text, source_text, sub_shingles=cached_sub_shingles, sub_tokens=cached_sub_norm_tokens
                )
                lexical_sim = float(tfidf_score)

                # Paraphrase semantic layer: evaluate top candidate sources with high relevance
                if cand_rank < 3 and (shingle_containment > 0.02 or exact_phrases or tfidf_score > 0.12):
                    semantic_cov, flagged_pairs = self.hybrid_checker.compute_semantic_matches(

                        full_text, source_text, sub_embeddings=cached_sub_embeddings, sub_sents=cached_sub_sents

                    )

                else:

                    semantic_cov, flagged_pairs = 0.0, []



                composite_sim = (

                    (0.45 * shingle_containment)

                    + (0.20 * lexical_sim)

                    + (0.35 * semantic_cov)

                )



                if winnow_count == 0 and exact_count == 0:
                    for phrase in exact_phrases:
                        all_matches.append({
                            'submitted_text': phrase,
                            'source_text': phrase,
                            'similarity': 1.0,
                            'match_type': 'phrase',
                            'source': source,
                            'source_index': source_index,
                        })

                for pair in flagged_pairs:
                    if pair.get('similarity', 0) >= 80.0 or (winnow_count == 0 and exact_count == 0 and phrase_count == 0):
                        all_matches.append({
                            'submitted_text': pair['submitted_sentence'],
                            'source_text': pair['matched_source_sentence'],
                            'similarity': pair['similarity'] / 100.0,
                            'match_type': 'exact' if pair['match_type'] == 'Exact/Near-Exact' else 'fuzzy',
                            'source': source,
                            'source_index': source_index,
                        })



                # Optional live AI API semantic paraphrase audit (Google Gemini / OpenAI)

                if self.ai_api_client.is_api_available(task_type='paraphrase') and composite_sim > 0.15:

                    try:

                        ai_para = self.ai_api_client.detect_semantic_plagiarism(full_text, source_text)

                        for ai_pair in ai_para.get('matched_pairs', []):

                            all_matches.append({

                                'submitted_text': ai_pair.get('sub_passage', ''),

                                'source_text': ai_pair.get('src_passage', ''),

                                'similarity': float(ai_pair.get('similarity', 0.8)),

                                'match_type': 'fuzzy',

                                'source': source,

                                'source_index': source_index,

                            })

                    except Exception as ai_e:

                        logger.debug(f"AI API semantic plagiarism check skipped: {ai_e}")



                # Register hybrid metrics with scorer for source-level breakdown

                scorer.set_source_hybrid_metrics(

                    source_id=str(source.id),

                    composite_similarity_pct=round(composite_sim * 100, 1),

                    exact_shingle_containment_pct=round(shingle_containment * 100, 1),

                    lexical_tfidf_pct=round(lexical_sim * 100, 1),

                    semantic_paraphrase_pct=round(semantic_cov * 100, 1),

                    exact_matched_shingles=exact_phrases[:5],

                    flagged_sentences=flagged_pairs,

                )



            # Pre-load extracted text character ranges for ultra-fast in-memory position lookups

            import bisect

            et_records = list(

                extracted_texts.values('page_number', 'paragraph_number', 'char_start', 'char_end')

                .order_by('char_start')

            )

            et_starts = [et['char_start'] for et in et_records]



            def _resolve_page_para(c_start):
                if not et_records or c_start is None:
                    return 1, 1
                for et in et_records:
                    s = et.get('char_start')
                    e = et.get('char_end')
                    if s is not None and e is not None and s <= c_start <= e:
                        return et['page_number'], et['paragraph_number']
                idx = bisect.bisect_right(et_starts, c_start) - 1
                if 0 <= idx < len(et_records):
                    return et_records[idx]['page_number'], et_records[idx]['paragraph_number']
                return 1, 1



            matched_passage_objects = []

            # Turnitin-style coalescing: merge overlapping and adjacent match fragments per source
            coalesced_matches = []
            matches_by_src = defaultdict(list)
            for m in all_matches:
                s_obj = m.get('source')
                s_id = str(s_obj.id) if s_obj else 'unknown'
                matches_by_src[s_id].append(m)

            for s_id, s_matches in matches_by_src.items():
                for m in s_matches:
                    if m.get('submitted_start') is None:
                        m['submitted_start'] = self._estimate_char_position(full_text, m['submitted_text'], start_from=0)
                    if m.get('submitted_end') is None:
                        m['submitted_end'] = (m['submitted_start'] or 0) + len(m['submitted_text'])

                s_matches.sort(key=lambda x: (x.get('submitted_start') or 0))
                merged_src = []
                for m in s_matches:
                    if not merged_src:
                        merged_src.append(m)
                    else:
                        prev = merged_src[-1]
                        m_start = m.get('submitted_start') or 0
                        m_end = m.get('submitted_end') or (m_start + len(m['submitted_text']))
                        prev_start = prev.get('submitted_start') or 0
                        prev_end = prev.get('submitted_end') or (prev_start + len(prev['submitted_text']))

                        # If overlapping or within 30 characters (~5 words)
                        if m_start <= prev_end + 30:
                            new_end = max(prev_end, m_end)
                            prev['submitted_end'] = new_end
                            prev['submitted_text'] = full_text[prev_start:new_end].strip()
                            if m.get('source_text') and m['source_text'] not in prev.get('source_text', ''):
                                prev['source_text'] = (prev.get('source_text', '') + ' ' + m.get('source_text', '')).strip()
                        else:
                            merged_src.append(m)
                coalesced_matches.extend(merged_src)

            # Deduplicate matching spans and apply exclusions
            for match in coalesced_matches:

                should_exclude, reason, uncertain = self.exclusion_engine.should_exclude(
                    match, full_text
                )



                # Character positions

                char_start = match.get('submitted_start')

                if char_start is None:

                    char_start = self._estimate_char_position(full_text, match['submitted_text'], start_from=0)

                char_end = match.get('submitted_end')

                if char_end is None:

                    char_end = char_start + len(match['submitted_text'])



                # Map character positions to discrete word indices

                w_start, w_end = self._char_span_to_word_span(sub_tokens, char_start, char_end)



                source_obj = match.get('source')

                source_id = str(source_obj.id) if source_obj else None

                source_title = source_obj.title if source_obj else ''



                if char_start is not None and et_records:
                    sub_page, sub_para = _resolve_page_para(char_start)
                else:
                    sub_page = match.get('submitted_page') or 1
                    sub_para = match.get('submitted_para') or 1



                mp = MatchedPassage(

                    report=report,

                    submitted_text=match['submitted_text'][:5000],

                    source_text=match.get('source_text', '')[:5000],

                    submitted_page=sub_page,

                    submitted_paragraph=sub_para,

                    submitted_char_start=char_start,

                    submitted_char_end=char_end,

                    source=source_obj,

                    source_page=match.get('source_page'),

                    source_paragraph=match.get('source_para'),

                    match_type=match['match_type'],

                    similarity_score=match.get('similarity', 1.0),

                    word_count=len(match['submitted_text'].split()),

                    source_index=match.get('source_index', 0),

                    is_excluded=should_exclude,

                    exclusion_reason=reason,

                )

                matched_passage_objects.append(mp)



                # Register non-excluded verified spans with word position scorer

                if not should_exclude:

                    scorer.add_match_span(

                        word_start=w_start,

                        word_end=w_end,

                        source_id=source_id,

                        source_name=source_title,

                        source_category=source_obj.get_source_type_display() if source_obj else 'Submitted Document',

                        source_url=getattr(source_obj, 'url', ''),

                        match_type=match['match_type'],

                        similarity=match.get('similarity', 1.0),

                    )



            # Persist all matched passages in batch

            if matched_passage_objects:

                MatchedPassage.objects.bulk_create(matched_passage_objects, batch_size=500)



            # Calculate word-level non-overlapping similarity

            score_result = scorer.calculate()



            # Synchronize each MatchedPassage source_index with final ranked Top Sources

            for s_info in score_result['sources']:

                s_id = s_info.get('source_id')

                final_rank = s_info.get('rank', 1)

                if s_id:

                    MatchedPassage.objects.filter(report=report, source_id=s_id).update(source_index=final_rank)



            # Persist comprehensive report metrics

            report.overall_similarity = score_result['overall_similarity']

            report.unfiltered_similarity = score_result['unfiltered_similarity']

            report.exact_similarity = score_result['exact_similarity']

            report.near_duplicate_similarity = score_result['near_duplicate_similarity']

            report.total_words = total_words

            report.eligible_words = score_result['eligible_words']

            report.excluded_words = score_result['excluded_words']

            report.matched_words = score_result['matched_words']

            report.source_breakdown = score_result['sources']

            report.source_count = len(score_result['sources'])



            report.exact_match_count = exact_count

            report.phrase_match_count = phrase_count

            report.fuzzy_match_count = fuzzy_count

            if score_result['overall_similarity'] == 0:
                if getattr(self, 'last_search_meta', {}).get('failed_sources') and not getattr(self, 'last_search_meta', {}).get('sources_checked'):
                    report.status = SimilarityReport.Status.SOURCE_UNAVAILABLE
                elif getattr(self, 'last_search_meta', {}).get('failed_sources'):
                    report.status = SimilarityReport.Status.PARTIALLY_CHECKED
                else:
                    report.status = SimilarityReport.Status.COMPLETED
            else:
                report.status = SimilarityReport.Status.COMPLETED

            report.processing_time_seconds = round(time.time() - start_time, 2)

            if not sources_checked and source_refs:
                for s in source_refs[:10]:
                    sources_checked.append({
                        'name': s.title,
                        'type': s.get_source_type_display() if hasattr(s, 'get_source_type_display') else 'Academic Repository',
                        'tfidf_similarity': 0.0,
                    })

            if integrity_flags:
                if not report.exclusion_settings:
                    report.exclusion_settings = {}
                report.exclusion_settings['integrity_flags'] = integrity_flags
                report.limitations = {'integrity_flags': integrity_flags}

            report.sources_checked = sources_checked

            report.save()



            # Update document status

            document.status = Document.Status.COMPLETED

            document.error_message = ''

            document.save(update_fields=['status', 'error_message'])



            logger.info(

                f"Analysis completed for '{document.title}': "

                f"{score_result['overall_similarity']:.1f}% similarity, "

                f"{report.source_count} sources, "

                f"{time.time() - start_time:.1f}s"

            )



            return report



        except Exception as e:

            logger.error(f"Analysis failed for document {document.id}: {e}", exc_info=True)

            report.status = SimilarityReport.Status.FAILED

            report.error_message = str(e)

            report.processing_time_seconds = time.time() - start_time

            report.save()



            document.status = Document.Status.FAILED

            document.error_message = f"Analysis error: {str(e)}"

            document.save(update_fields=['status', 'error_message'])



            return report



    def _extract_distinctive_queries(self, document, full_text: str) -> List[str]:
        """Extracts distinctive titles and salient phrases from document across its full length for academic & web queries."""
        queries = []
        doc_title = (getattr(document, 'title', '') or '').strip()
        # Clean title of common student submission suffixes/patterns
        cleaned_title = re.sub(r'(?i)(plag[f_]?\w*|reduced|\bnew\b|\bfinal\b|\bcorrected\b|\brevised\b|\bversion\b|\bv\d+\b|\bcopy\b|\bthesis\b|\bpaper\b|\bdraft\b|\d{6,})', ' ', doc_title)
        cleaned_title = re.sub(r'[^\w\s-]', ' ', cleaned_title)
        cleaned_title = ' '.join(w for w in cleaned_title.split() if len(w) > 2)
        if len(cleaned_title.split()) >= 3:
            queries.append(cleaned_title[:150])

        # Extract salient headings or title candidate from the beginning of text
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        for line in lines[:15]:
            clean_line = re.sub(r'^[#*\s\d.]+', '', line).strip()
            clean_line = re.sub(r'(?i)^(chapter|section|part)\s+\d+[:.\s-]*', '', clean_line).strip()
            w_count = len(clean_line.split())
            if 4 <= w_count <= 18 and clean_line.lower() not in [q.lower() for q in queries] and not clean_line.lower().startswith(('overview', 'introduction')):
                queries.append(clean_line[:150])
                break

        # Extract distinctive, domain-specific phrases across evenly distributed sections of the document
        paras = [p.strip() for p in full_text.split('\n\n') if len(p.strip()) > 80]
        stopwords = {
            'this', 'that', 'with', 'from', 'have', 'were', 'which', 'their', 'there',
            'about', 'would', 'could', 'should', 'these', 'those', 'being', 'between',
            'into', 'more', 'also', 'such', 'other', 'than', 'some', 'when', 'chapter',
            'presents', 'presented', 'overview', 'context', 'inspiration', 'discusses',
            'figure', 'table', 'equation', 'shown', 'shows', 'illustrates', 'using'
        }

        if paras:
            step = max(1, len(paras) // 6)
            for idx in range(0, len(paras), step):
                p = paras[idx]
                sents = re.split(r'(?<=[.!?])\s+', p)
                for s in sents:
                    clean_s = re.sub(r'[^\w\s]', ' ', s).strip()
                    words = [w for w in clean_s.split() if len(w) > 2]
                    meaningful = [w for w in words if w.lower() not in stopwords]
                    if 8 <= len(words) <= 24 and len(meaningful) >= 5:
                        phrase = " ".join(words[:12])
                        if phrase.lower() not in [q.lower() for q in queries]:
                            queries.append(phrase)
                            break
                if len(queries) >= 8:
                    break

        # Extract distinctive domain technical trigrams and salient phrases
        raw_words = [w.lower() for w in re.findall(r'[a-zA-Z\u0900-\u097F]{3,}', full_text)]
        meaningful_tokens = [w for w in raw_words if w not in stopwords and len(w) > 2]
        if len(meaningful_tokens) >= 3:
            from collections import Counter
            trigrams = Counter([' '.join(meaningful_tokens[i:i+3]) for i in range(len(meaningful_tokens)-2)])
            for tg, count in trigrams.most_common(5):
                if count >= 3 and tg.lower() not in [q.lower() for q in queries] and not tg.startswith('https doi') and not tg.startswith('doi org'):
                    queries.append(tg)

        return queries[:8]

    def _get_comparison_sources(self, document, full_text=""):

        """Get reference sources to compare against, including Playwright live web search."""

        sources = list(

            ReferenceSource.objects.filter(is_active=True)

            .exclude(document=document)

            .select_related('document', 'institution')

        )



        # Filter out self-match drafts / duplicates from the same user if exclude_self_match is active
        # Excludes only exact duplicates or prior revisions of the SAME student's paper,
        # while preserving other distinct student papers and institutional works.
        exclude_self = self.exclusion_settings.get('exclude_self_match', True)

        if exclude_self and document.uploaded_by:
            doc_title_norm = re.sub(r'[^\w]', '', (document.title or '').lower())

            def is_same_work_draft(s):
                if not s.document:
                    return False
                if s.document.is_reference:
                    return False
                if document.file_hash and s.document.file_hash == document.file_hash:
                    return True
                s_title_norm = re.sub(r'[^\w]', '', (s.document.title or s.title or '').lower())
                if doc_title_norm and s_title_norm and (doc_title_norm in s_title_norm or s_title_norm in doc_title_norm):
                    return True
                return False

            sources = [s for s in sources if not is_same_work_draft(s)]

        if document.file_hash:

            sources = [

                s for s in sources

                if not (s.document and s.document.file_hash == document.file_hash)

            ]



        existing_source_doc_ids = {str(s.document_id) for s in sources if s.document_id}



        # Check live academic databases & internet sources using modular connectors
        check_web = self.exclusion_settings.get('check_web_sources', True)
        search_metadata = {'sources_checked': [], 'failed_sources': []}

        if check_web and full_text and len(full_text.split()) >= 8:
            try:
                from sources.providers import multi_source_search
                queries = self._extract_distinctive_queries(document, full_text)
                if queries:
                    search_res = multi_source_search(
                        queries=queries,
                        max_results_per_source=3,
                        timeout_seconds=15.0,
                        exclude_document_id=document.id,
                        target_document=document,
                    )
                    search_metadata['sources_checked'] = search_res.get('sources_checked', [])
                    search_metadata['failed_sources'] = search_res.get('failed_sources', [])

                    inst = document.uploaded_by.institution if (document and document.uploaded_by) else None
                    doc_id_str = str(document.id) if document else None
                    doc_title_clean = (document.title or '').strip().lower() if document else ''

                    for prov_res in search_res.get('results', []):
                        if doc_id_str:
                            if doc_id_str in (prov_res.url or ''):
                                continue
                            if doc_title_clean and (prov_res.title or '').strip().lower() == doc_title_clean:
                                continue
                        if prov_res.text and len(prov_res.text.strip()) > 25:
                            ref_obj = prov_res.to_reference_source(institution=inst)
                            if ref_obj:
                                if ref_obj.document_id and str(ref_obj.document_id) == doc_id_str:
                                    continue
                                if doc_id_str and doc_id_str in (ref_obj.url or ''):
                                    continue
                                if not any(str(s.id) == str(ref_obj.id) for s in sources):
                                    sources.append(ref_obj)
            except Exception as search_e:
                logger.warning(f"Multi-source academic/web search exception: {search_e}")

            # Optional Playwright headless crawler if explicitly enabled
            if getattr(settings, 'ENABLE_PLAYWRIGHT_SEARCH', False):
                try:
                    from .playwright_scraper import PlaywrightPlagiarismChecker
                    min_words = self.exclusion_settings.get('min_match_words', 8)
                    checker = PlaywrightPlagiarismChecker(headless=True, timeout_ms=6000)
                    web_sources = checker.search_and_retrieve_sources(
                        full_text=full_text,
                        min_words=min_words,
                        max_sources=4,
                        target_document=document,
                    )
                    for ws in web_sources:
                        if not any(str(s.id) == str(ws.id) for s in sources):
                            sources.append(ws)
                except Exception as pw_e:
                    logger.debug(f"Playwright web crawl skipped: {pw_e}")

        self.last_search_meta = search_metadata



        # Also compare against other uploaded documents (not self)

        other_docs = Document.objects.filter(

            status__in=[Document.Status.EXTRACTED, Document.Status.COMPLETED],

            is_deleted=False,

        ).exclude(id=document.id)



        # exclude_self_match filters out prior drafts/revisions of the SAME student's paper
        exclude_self = self.exclusion_settings.get('exclude_self_match', True)
        if exclude_self and document.uploaded_by:
            doc_title_norm = re.sub(r'[^\w]', '', (document.title or '').lower())
            excluded_ids = set()
            for od in other_docs:
                if od.is_reference:
                    continue
                od_title_norm = re.sub(r'[^\w]', '', (od.title or '').lower())
                if doc_title_norm and od_title_norm and (doc_title_norm in od_title_norm or od_title_norm in doc_title_norm):
                    excluded_ids.add(od.id)
            if excluded_ids:
                other_docs = other_docs.exclude(id__in=excluded_ids)

        # Always exclude identical file-hash duplicates of the same document

        if document.file_hash:

            other_docs = other_docs.exclude(file_hash=document.file_hash)



        # Check assignment-level comparison

        if document.assignment and document.assignment.allow_self_comparison:

            assignment_docs = Document.objects.filter(

                assignment=document.assignment,

                status__in=[Document.Status.EXTRACTED, Document.Status.COMPLETED],

                is_deleted=False,

            ).exclude(id=document.id)



            for doc in assignment_docs:

                if str(doc.id) not in existing_source_doc_ids:

                    sources.append(self._doc_to_reference(doc))

                    existing_source_doc_ids.add(str(doc.id))



        # Add other institution documents as potential sources

        # Ensure every other document is included even if it already has a ReferenceSource

        for doc in other_docs[:50]:

            if str(doc.id) not in existing_source_doc_ids:

                sources.append(self._doc_to_reference(doc))

                existing_source_doc_ids.add(str(doc.id))



        # Absolute guarantee: eliminate any candidate that matches the target document itself or prior drafts from the same author
        clean_sources = []
        doc_id_str = str(document.id) if document else None
        doc_title_clean = (document.title or '').strip().lower() if document else ''
        user = getattr(document, 'uploaded_by', None) if document else None
        user_doc_ids = set(str(uid) for uid in Document.objects.filter(uploaded_by=user).values_list('id', flat=True)) if user else set()

        norm_doc_title = re.sub(r'[^\w]', '', doc_title_clean)

        for s in sources:
            if doc_id_str:
                if s.document_id and str(s.document_id) == doc_id_str:
                    continue
                if s.url and doc_id_str in s.url:
                    continue
            if user_doc_ids and s.document_id and str(s.document_id) in user_doc_ids:
                continue
            if s.url and any(f'urn:proovexa:doc:{uid}' in s.url for uid in user_doc_ids):
                continue
            s_title_clean = (s.title or '').strip().lower()
            if s_title_clean and s_title_clean == doc_title_clean:
                if s.source_type in (ReferenceSource.SourceType.UPLOADED, ReferenceSource.SourceType.INSTITUTIONAL):
                    continue
            norm_s_title = re.sub(r'[^\w]', '', s_title_clean)
            if len(norm_doc_title) >= 6 and len(norm_s_title) >= 6:
                if (norm_doc_title in norm_s_title or norm_s_title in norm_doc_title) and s.source_type in (ReferenceSource.SourceType.UPLOADED, ReferenceSource.SourceType.INSTITUTIONAL):
                    continue
            clean_sources.append(s)

        logger.info(f"_get_comparison_sources: {len(clean_sources)} sources found for '{document.title}'")

        return clean_sources



    def _doc_to_reference(self, document):

        """Convert a Document to a persisted ReferenceSource."""

        from reports.criteria import extract_academic_title_from_doc
        acad_title = extract_academic_title_from_doc(document)
        source_title = (acad_title or document.title)[:500]

        ref, _ = ReferenceSource.objects.get_or_create(

            document=document,

            defaults={

                'title': source_title,

                'author': document.uploaded_by.get_full_name() if document.uploaded_by else '',

                'source_type': ReferenceSource.SourceType.UPLOADED,

                'url': f'/documents/{document.id}/',

                'is_active': True,

            }

        )

        return ref



    def _get_source_text(self, source):

        """Get full text from a reference source, caching to retrieved_text when populated from ExtractedText."""

        if source.retrieved_text:

            return source.retrieved_text



        if source.document:

            texts = ExtractedText.objects.filter(

                document=source.document

            ).order_by('page_number', 'paragraph_number')

            full_text = '\n\n'.join(t.content for t in texts)

            if full_text:

                # Cache back to avoid repeated DB hits

                try:

                    source.retrieved_text = full_text

                    source.word_count = len(full_text.split())

                    source.save(update_fields=['retrieved_text', 'word_count'])

                except Exception:

                    pass

            return full_text



        return ''



    def _get_document_pages(self, document):

        """Get page structure for a document."""

        texts = ExtractedText.objects.filter(

            document=document

        ).order_by('page_number', 'paragraph_number')



        pages = []

        current_page = None

        for t in texts:

            if current_page is None or current_page['page_number'] != t.page_number:

                current_page = {'page_number': t.page_number, 'paragraphs': []}

                pages.append(current_page)

            current_page['paragraphs'].append({

                'text': t.content,

                'para_number': t.paragraph_number,

            })

        return pages



    def _estimate_char_position(self, full_text, match_text, start_from=0):
        """Fast character position estimation in full text without catastrophic regex backtracking."""
        if not match_text:
            return 0
        clean_match = match_text.strip().lower()
        # 1. Try first 80 chars
        snippet = clean_match[:80]
        pos = full_text.lower().find(snippet, max(0, start_from))
        if pos != -1:
            return pos
        pos = full_text.lower().find(snippet)
        if pos != -1:
            return pos
        # 2. Try first 30 chars
        if len(clean_match) > 30:
            snippet_short = clean_match[:30]
            pos = full_text.lower().find(snippet_short, max(0, start_from))
            if pos != -1:
                return pos
            pos = full_text.lower().find(snippet_short)
            if pos != -1:
                return pos
        # 3. Try first 3-4 words with simple substring find
        words = clean_match.split()
        if len(words) >= 2:
            w_snippet = " ".join(words[:min(4, len(words))])
            pos = full_text.lower().find(w_snippet, max(0, start_from))
            if pos != -1:
                return pos
            pos = full_text.lower().find(w_snippet)
            if pos != -1:
                return pos
        return 0

    def _char_span_to_word_span(self, tokens, char_start, char_end):
        """Maps character offsets [char_start, char_end] to word indices [w_start, w_end] in O(log N)."""
        if not tokens:
            return 0, 0
        import bisect
        token_starts = getattr(self, '_cached_token_starts', None)
        token_ends = getattr(self, '_cached_token_ends', None)
        if token_starts is None or len(token_starts) != len(tokens):
            token_starts = [t.start_char for t in tokens]
            token_ends = [t.end_char for t in tokens]
            self._cached_token_starts = token_starts
            self._cached_token_ends = token_ends

        w_start = bisect.bisect_left(token_ends, char_start)
        if w_start >= len(tokens):
            w_start = len(tokens) - 1
        w_end = bisect.bisect_right(token_starts, char_end) - 1
        if w_end < w_start:
            w_end = w_start
        return w_start, min(w_end, len(tokens) - 1)
