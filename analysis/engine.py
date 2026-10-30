"""
Core similarity analysis engine.
Orchestrates all comparison methods, applies exclusions, and generates reports.
"""
import re
import time
import logging
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

    def __init__(self, exclusion_settings=None):
        self.exclusion_settings = exclusion_settings or {
            'exclude_bibliography': False,
            'exclude_quotations': False,
            'exclude_citations': False,
            'min_match_words': getattr(settings, 'MIN_MATCH_WORD_COUNT', 8),
            'exclude_common_phrases': False,
            'common_phrases_list': [],
            'exclude_sources': [],
            'exclude_self_match': True,
            'check_web_sources': True,
        }

        # Initialize comparators
        min_words = self.exclusion_settings.get('min_match_words', 8)
        ngram_size = getattr(settings, 'NGRAM_SIZE', 5)

        self.winnowing_engine = WinnowingEngine(k=min_words, w=4)
        self.exact_comparator = ExactMatchComparator(min_word_count=min_words)
        self.ngram_comparator = NGramComparator(n=ngram_size)
        self.fuzzy_comparator = FuzzyComparator(threshold=0.75)
        self.tfidf_comparator = TFIDFComparator()
        self.hybrid_checker = TurnitinStyleChecker(shingle_size=min_words, semantic_threshold=0.75)
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
                # No sources to compare - report 0% similarity
                report.overall_similarity = 0.0
                report.total_words = total_words
                report.matched_words = 0
                report.source_count = 0
                report.status = SimilarityReport.Status.COMPLETED
                report.processing_time_seconds = time.time() - start_time
                report.sources_checked = ['No reference sources available for comparison']
                report.save()
                document.status = Document.Status.COMPLETED
                document.save(update_fields=['status'])
                return report

            # Step 1: Tokenize submitted document with offsets and compute Winnowing fingerprints
            sub_fps, sub_tokens = self.winnowing_engine.compute_fingerprints(full_text)
            total_words = len(sub_tokens) if sub_tokens else (document.word_count or len(full_text.split()))

            # Initialize academic word-position scorer
            scorer = AcademicSimilarityScorer(total_word_count=total_words, full_text=full_text)
            min_words = self.exclusion_settings.get('min_match_words', 8)

            # Detect document-level exclusion regions (e.g. bibliography sections)
            if self.exclusion_settings.get('exclude_bibliography'):
                bib_matches = list(re.finditer(r'(?:^|\n)\s*(?:References|Bibliography|Works Cited)\s*(?:\n|$)', full_text, re.IGNORECASE))
                valid_bib = None
                for m in bib_matches:
                    if m.start() > 2000 or m.start() > len(full_text) * 0.3:
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
                # No sources with text to compare against
                report.overall_similarity = 0.0
                report.total_words = total_words
                report.matched_words = 0
                report.source_count = 0
                report.status = SimilarityReport.Status.COMPLETED
                report.processing_time_seconds = time.time() - start_time
                report.sources_checked = [f'{len(sources)} reference sources found but none had extractable text']
                report.save()
                document.status = Document.Status.COMPLETED
                document.save(update_fields=['status'])
                return report

            # Get candidate sources by TF-IDF similarity
            candidates = self.tfidf_comparator.compare_batch(full_text, source_texts)
            logger.info(f"TF-IDF pre-filter: {len(candidates)} candidate sources above threshold")

            # Limit to top candidates for detailed multi-method analysis (8 is standard for high recall + speed)
            max_candidates = 60
            top_candidates = candidates[:max_candidates]

            # Ensure all live crawled web sources are explicitly included in top_candidates for full matching
            cand_indices = {c[0] for c in top_candidates}
            for s_idx, s_ref in enumerate(source_refs):
                if getattr(s_ref, 'source_type', '') == ReferenceSource.SourceType.WEB and s_idx not in cand_indices:
                    top_candidates.append((s_idx, 0.50))

            all_matches = []
            source_index = 0
            sources_checked = []
            exact_count = 0
            phrase_count = 0
            fuzzy_count = 0
            winnow_count = 0

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
                    sub_fps, src_fps, full_text, source_text, min_words=min_words
                )
                for wp in winnow_passages:
                    wp['source'] = source
                    wp['source_index'] = source_index
                    wp['match_type'] = 'exact'
                    all_matches.append(wp)
                    winnow_count += 1
                    exact_count += 1

                # Method B: Exact String Matching
                exact_result = self.exact_comparator.compare(
                    full_text, source_text, pages, source_pages
                )
                for match in exact_result.matches:
                    match['source'] = source
                    match['source_index'] = source_index
                    match['match_type'] = 'exact'
                    all_matches.append(match)
                    exact_count += 1

                # Method C: N-Gram Phrase Matching
                ngram_result = self.ngram_comparator.compare(
                    full_text, source_text, pages, source_pages
                )
                for match in ngram_result.matches:
                    match['source'] = source
                    match['source_index'] = source_index
                    match['match_type'] = 'phrase'
                    all_matches.append(match)
                    phrase_count += 1

                # Method D: Near-Duplicate / Fuzzy Matching (run on top 4 candidates with non-trivial similarity)
                if cand_rank < 4 and tfidf_score > 0.08:
                    fuzzy_result = self.fuzzy_comparator.compare(
                        full_text, source_text, pages, source_pages
                    )
                    for match in fuzzy_result.matches:
                        match['source'] = source
                        match['source_index'] = source_index
                        match['match_type'] = 'fuzzy'
                        all_matches.append(match)
                        fuzzy_count += 1

                # Method E: Turnitin 3-Tier Hybrid Evaluation (Shingle Containment, Lexical, Semantic Paraphrase)
                shingle_containment, exact_phrases = self.hybrid_checker.compute_shingle_containment(
                    full_text, source_text
                )
                lexical_sim = self.hybrid_checker.compute_lexical_similarity(
                    full_text, source_text
                )
                if cand_rank < 4 or shingle_containment > 0.05 or lexical_sim > 0.10:
                    semantic_cov, flagged_pairs = self.hybrid_checker.compute_semantic_matches(
                        full_text, source_text
                    )
                else:
                    semantic_cov, flagged_pairs = 0.0, []

                composite_sim = (
                    (0.45 * shingle_containment)
                    + (0.20 * lexical_sim)
                    + (0.35 * semantic_cov)
                )

                for pair in flagged_pairs:
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

            # Deduplicate matching spans and apply exclusions
            for match in all_matches:
                should_exclude, reason, uncertain = self.exclusion_engine.should_exclude(
                    match, full_text
                )

                # Character positions
                char_start = match.get('submitted_start')
                if char_start is None:
                    char_start = self._estimate_char_position(full_text, match['submitted_text'], start=True)
                char_end = match.get('submitted_end') or (char_start + len(match['submitted_text']))

                # Map character positions to discrete word indices
                w_start, w_end = self._char_span_to_word_span(sub_tokens, char_start, char_end)

                # Save match record to database
                source_obj = match.get('source')
                if source_obj and not ReferenceSource.objects.filter(id=source_obj.id).exists():
                    try:
                        source_obj.save()
                    except Exception:
                        source_obj = None
                source_id = str(source_obj.id) if source_obj else None
                source_title = source_obj.title if source_obj else ''

                sub_page = match.get('submitted_page')
                sub_para = match.get('submitted_para')
                if not sub_page or not sub_para:
                    et_hit = extracted_texts.filter(char_start__lte=char_start, char_end__gte=char_start).first()
                    if not et_hit and char_start is not None:
                        et_hit = extracted_texts.filter(char_start__lte=char_start).order_by('-char_start').first()
                    if et_hit:
                        sub_page = et_hit.page_number
                        sub_para = et_hit.paragraph_number
                    else:
                        sub_page = 1
                        sub_para = 1

                mp = MatchedPassage.objects.create(
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
            report.status = SimilarityReport.Status.COMPLETED
            report.processing_time_seconds = round(time.time() - start_time, 2)
            report.sources_checked = sources_checked
            report.save()

            # Update document status
            document.status = Document.Status.COMPLETED
            document.save(update_fields=['status'])

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

    def _get_comparison_sources(self, document, full_text=""):
        """Get reference sources to compare against, including Playwright live web search."""
        sources = list(
            ReferenceSource.objects.filter(is_active=True)
            .exclude(document=document)
            .select_related('document', 'institution')
        )
        existing_source_doc_ids = {str(s.document_id) for s in sources if s.document_id}

        # Check live internet sources using Playwright headless browser
        check_web = self.exclusion_settings.get('check_web_sources', True)
        if check_web and full_text and len(full_text.split()) >= 14:
            try:
                from .playwright_scraper import PlaywrightPlagiarismChecker
                min_words = self.exclusion_settings.get('min_match_words', 8)
                checker = PlaywrightPlagiarismChecker(headless=True, timeout_ms=12000)
                web_sources = checker.search_and_retrieve_sources(
                    full_text=full_text,
                    min_words=min_words,
                    max_sources=6,
                    target_document=document,
                )
                for ws in web_sources:
                    if not any(str(s.id) == str(ws.id) for s in sources):
                        sources.append(ws)
            except Exception as pw_e:
                logger.warning(f"Playwright web plagiarism search skipped: {pw_e}")

        # Also compare against other uploaded documents (not self)
        other_docs = Document.objects.filter(
            status__in=[Document.Status.EXTRACTED, Document.Status.COMPLETED],
            is_deleted=False,
        ).exclude(id=document.id)

        # exclude_self_match only applies to same-user STUDENT drafts;
        # staff/admin/teacher uploads are ALWAYS compared against all documents
        exclude_self = self.exclusion_settings.get('exclude_self_match', True)
        is_staff_user = bool(
            document.uploaded_by and (
                getattr(document.uploaded_by, 'is_admin', False) or
                getattr(document.uploaded_by, 'is_teacher', False) or
                getattr(document.uploaded_by, 'is_superuser', False) or
                getattr(document.uploaded_by, 'is_staff', False)
            )
        )
        if exclude_self and not is_staff_user and document.uploaded_by:
            other_docs = other_docs.filter(
                Q(is_reference=True) | ~Q(uploaded_by=document.uploaded_by)
            )

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

        logger.info(f"_get_comparison_sources: {len(sources)} sources found for '{document.title}'")
        return sources

    def _doc_to_reference(self, document):
        """Convert a Document to a persisted ReferenceSource."""
        ref, _ = ReferenceSource.objects.get_or_create(
            document=document,
            defaults={
                'title': document.title,
                'author': document.uploaded_by.get_full_name() if document.uploaded_by else '',
                'source_type': ReferenceSource.SourceType.UPLOADED,
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

    def _estimate_char_position(self, full_text, match_text, start=True):
        """Estimate character position of a match in the full text."""
        pos = full_text.lower().find(match_text.lower()[:100])
        return max(pos, 0)

    def _char_span_to_word_span(self, tokens, char_start, char_end):
        """Maps character offsets [char_start, char_end] to word indices [w_start, w_end]."""
        if not tokens:
            return 0, 0
        w_start = 0
        w_end = len(tokens) - 1
        for idx, t in enumerate(tokens):
            if t.start_char <= char_start <= t.end_char or t.start_char >= char_start:
                w_start = idx
                break
        for idx in range(w_start, len(tokens)):
            if tokens[idx].end_char >= char_end:
                w_end = idx
                break
            w_end = idx
        return w_start, max(w_start, w_end)

