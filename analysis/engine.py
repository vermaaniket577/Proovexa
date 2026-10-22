"""
Core similarity analysis engine.
Orchestrates all comparison methods, applies exclusions, and generates reports.
"""
import time
import logging
from django.conf import settings
from django.utils import timezone

from .comparators import ExactMatchComparator, NGramComparator, FuzzyComparator, TFIDFComparator
from .exclusions import ExclusionEngine
from .scoring import SimilarityScorer
from .models import SimilarityReport, MatchedPassage, ProcessingJob
from documents.models import Document, ExtractedText, ReferenceSource

logger = logging.getLogger(__name__)


class AnalysisEngine:
    """
    Main similarity analysis engine.
    
    Coordinates multiple comparison methods, applies exclusion rules,
    calculates scores without double-counting, and persists results.
    """

    def __init__(self, exclusion_settings=None):
        self.exclusion_settings = exclusion_settings or {
            'exclude_bibliography': False,
            'exclude_quotations': False,
            'exclude_citations': False,
            'min_match_words': getattr(settings, 'MIN_MATCH_WORD_COUNT', 5),
            'exclude_common_phrases': False,
            'common_phrases_list': [],
            'exclude_sources': [],
            'exclude_self_match': True,
        }

        # Initialize comparators
        min_words = self.exclusion_settings.get('min_match_words', 5)
        ngram_size = getattr(settings, 'NGRAM_SIZE', 5)

        self.exact_comparator = ExactMatchComparator(min_word_count=min_words)
        self.ngram_comparator = NGramComparator(n=ngram_size)
        self.fuzzy_comparator = FuzzyComparator(threshold=0.75)
        self.tfidf_comparator = TFIDFComparator()

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

            # Get reference sources to compare against
            sources = self._get_comparison_sources(document)

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

            # Initialize scorer
            scorer = SimilarityScorer(len(full_text), total_words)

            # Step 1: TF-IDF pre-filtering for efficiency
            source_texts = []
            source_refs = []
            for src in sources:
                text = self._get_source_text(src)
                if text:
                    source_texts.append(text)
                    source_refs.append(src)

            # Get candidate sources by TF-IDF similarity
            candidates = self.tfidf_comparator.compare_batch(full_text, source_texts)

            # Limit to top candidates for detailed analysis
            max_candidates = 20
            top_candidates = candidates[:max_candidates]

            all_matches = []
            source_index = 0
            sources_checked = []
            exact_count = 0
            phrase_count = 0
            fuzzy_count = 0

            for src_idx, tfidf_score in top_candidates:
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

                # Get source pages if available
                source_pages = None
                if source.document:
                    source_pages = self._get_document_pages(source.document)

                # Run exact matching
                exact_result = self.exact_comparator.compare(
                    full_text, source_text, pages, source_pages
                )
                for match in exact_result.matches:
                    match['source'] = source
                    match['source_index'] = source_index
                    match['match_type'] = 'exact'
                    all_matches.append(match)
                    exact_count += 1

                # Run n-gram matching
                ngram_result = self.ngram_comparator.compare(
                    full_text, source_text, pages, source_pages
                )
                for match in ngram_result.matches:
                    match['source'] = source
                    match['source_index'] = source_index
                    match['match_type'] = 'phrase'
                    all_matches.append(match)
                    phrase_count += 1

                # Run fuzzy matching
                fuzzy_result = self.fuzzy_comparator.compare(
                    full_text, source_text, pages, source_pages
                )
                for match in fuzzy_result.matches:
                    match['source'] = source
                    match['source_index'] = source_index
                    match['match_type'] = 'fuzzy'
                    all_matches.append(match)
                    fuzzy_count += 1

            # Apply exclusions and save matches
            for match in all_matches:
                should_exclude, reason, uncertain = self.exclusion_engine.should_exclude(
                    match, full_text
                )

                # Estimate character positions from word positions
                char_start = self._estimate_char_position(
                    full_text, match['submitted_text'], start=True
                )
                char_end = char_start + len(match['submitted_text'])

                # Save to database
                mp = MatchedPassage.objects.create(
                    report=report,
                    submitted_text=match['submitted_text'][:5000],  # Limit size
                    source_text=match.get('source_text', '')[:5000],
                    submitted_page=match.get('submitted_page', 1),
                    submitted_paragraph=match.get('submitted_para', 1),
                    submitted_char_start=char_start,
                    submitted_char_end=char_end,
                    source=match.get('source'),
                    source_page=match.get('source_page'),
                    source_paragraph=match.get('source_para'),
                    match_type=match['match_type'],
                    similarity_score=match.get('similarity', 0.0),
                    word_count=len(match['submitted_text'].split()),
                    source_index=match.get('source_index', 0),
                    is_excluded=should_exclude,
                    exclusion_reason=reason,
                )

                # Add non-excluded matches to scorer
                if not should_exclude:
                    source_id = str(match['source'].id) if match.get('source') else None
                    scorer.add_match_span(
                        char_start, char_end,
                        source_id=source_id,
                        match_type=match['match_type'],
                    )

            # Calculate final scores
            score_result = scorer.calculate_overall_similarity()

            # Update report
            report.overall_similarity = score_result['overall_similarity']
            report.total_words = total_words
            report.matched_words = score_result['matched_words_estimate']
            report.source_count = len(set(
                str(m['source'].id) for m in all_matches
                if m.get('source') and not self.exclusion_engine.should_exclude(m, full_text)[0]
            ))
            report.exact_match_count = exact_count
            report.phrase_match_count = phrase_count
            report.fuzzy_match_count = fuzzy_count
            report.status = SimilarityReport.Status.COMPLETED
            report.processing_time_seconds = time.time() - start_time
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

    def _get_comparison_sources(self, document):
        """Get reference sources to compare against."""
        sources = list(
            ReferenceSource.objects.filter(is_active=True)
            .exclude(document=document)
            .select_related('document', 'institution')
        )

        # Also compare against other uploaded documents (not self)
        exclude_self = self.exclusion_settings.get('exclude_self_match', True)
        other_docs = Document.objects.filter(
            status__in=[Document.Status.EXTRACTED, Document.Status.COMPLETED],
            is_deleted=False,
        ).exclude(id=document.id)

        if exclude_self:
            other_docs = other_docs.exclude(uploaded_by=document.uploaded_by)

        # Check assignment-level comparison
        if document.assignment and document.assignment.allow_self_comparison:
            assignment_docs = Document.objects.filter(
                assignment=document.assignment,
                status__in=[Document.Status.EXTRACTED, Document.Status.COMPLETED],
                is_deleted=False,
            ).exclude(id=document.id)

            for doc in assignment_docs:
                if not ReferenceSource.objects.filter(document=doc).exists():
                    sources.append(self._doc_to_reference(doc))

        # Add other institution documents as potential sources
        for doc in other_docs[:50]:  # Limit to prevent memory issues
            if not ReferenceSource.objects.filter(document=doc).exists():
                sources.append(self._doc_to_reference(doc))

        return sources

    def _doc_to_reference(self, document):
        """Convert a Document to a temporary ReferenceSource (not saved)."""
        ref = ReferenceSource(
            id=document.id,
            title=document.title,
            author=document.uploaded_by.get_full_name() if document.uploaded_by else '',
            source_type=ReferenceSource.SourceType.UPLOADED,
            document=document,
        )
        return ref

    def _get_source_text(self, source):
        """Get full text from a reference source."""
        if source.retrieved_text:
            return source.retrieved_text

        if source.document:
            texts = ExtractedText.objects.filter(
                document=source.document
            ).order_by('page_number', 'paragraph_number')
            return '\n\n'.join(t.content for t in texts)

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
