"""
Unit and Integration Tests for Dynamic Top Sources Engine.

Validates:
1. Greedy Set-Cover Token Attribution (unclaimed tokens, non-overlapping guarantee).
2. Sum of sources <= overall similarity index.
3. Minimum match threshold filtering (< 8 words relegated/skipped).
4. Percentage display formatting rules (0% omitted, < 1% as '<1%', >= 1% as rounded integer).
5. Multilingual tokenization (English, Devanagari Hindi, NFKC normalization).
6. 4-Color theme cycling (pink, blue, teal, purple).
7. Structured JSON payload data model conformity.
"""
from django.test import TestCase

from analysis.top_sources_service import (
    tokenize_multilingual,
    normalize_source_type,
    format_similarity_percentage,
    CandidateSource,
    calculate_non_overlapping_top_sources,
    TOP_SOURCES_THEMES,
)
from analysis.scoring import AcademicSimilarityScorer
from reports.criteria import compute_report_criteria
from documents.models import Document, ReferenceSource
from accounts.models import User, Institution
from analysis.models import SimilarityReport


class TopSourcesEngineTestCase(TestCase):
    """Test suite for Dynamic Top Sources calculation and formatting."""

    def test_multilingual_tokenization_english_and_hindi(self):
        """Verify tokenize_multilingual handles English and Devanagari Hindi with NFKC normalization."""
        # 1. English with hyphens and apostrophes
        english_text = "The state-of-the-art model doesn't fail on complex NLP tasks."
        en_tokens = tokenize_multilingual(english_text)
        self.assertIn("state-of-the-art", en_tokens)
        self.assertIn("doesn't", en_tokens)

        # 2. Hindi Devanagari text
        hindi_text = "साहित्यिक चोरी और शोध निष्ठा का विस्तृत विश्लेषण।"
        hi_tokens = tokenize_multilingual(hindi_text)
        # 8 words in this sentence
        self.assertEqual(len(hi_tokens), 8)
        self.assertNotIn("।", hi_tokens[-1])
        self.assertIn("साहित्यिक", hi_tokens)
        self.assertIn("चोरी", hi_tokens)
        self.assertIn("विश्लेषण", hi_tokens)

        # 3. Unicode normalization (combining characters)
        raw_accented = "re\u0301sume\u0301"  # NFD: e + combining acute
        tokens = tokenize_multilingual(raw_accented)
        self.assertEqual(tokens, ["résumé"])

    def test_source_type_normalization(self):
        """Verify normalize_source_type classifies categories into Publication, Internet, and Submitted works."""
        self.assertEqual(normalize_source_type("Academic Journal", "https://doi.org/10.1234/s123"), "Publication")
        self.assertEqual(normalize_source_type("crossref", "https://sciencedirect.com/article"), "Publication")
        self.assertEqual(normalize_source_type("web", "https://example.com/blog"), "Internet")
        self.assertEqual(normalize_source_type("internet", "sajhrm.co.za"), "Internet")
        self.assertEqual(normalize_source_type("student paper", ""), "Submitted works")
        self.assertEqual(normalize_source_type("uploaded", "", "Stanford University Submission"), "Submitted works")

    def test_percentage_formatting_rules(self):
        """Verify Turnitin percentage formatting: 0% omitted, <1% formatted as '<1%', >=1% rounded integer."""
        total = 1000

        # 0 words -> None
        display_0, pct_0 = format_similarity_percentage(0, total)
        self.assertIsNone(display_0)
        self.assertEqual(pct_0, 0.0)

        # 5 words -> 0.5% -> "<1%"
        display_5, pct_5 = format_similarity_percentage(5, total)
        self.assertEqual(display_5, "<1%")
        self.assertEqual(pct_5, 0.5)

        # 14 words -> 1.4% -> "1%"
        display_14, pct_14 = format_similarity_percentage(14, total)
        self.assertEqual(display_14, "1%")
        self.assertEqual(pct_14, 1.4)

        # 28 words -> 2.8% -> "3%"
        display_28, pct_28 = format_similarity_percentage(28, total)
        self.assertEqual(display_28, "3%")
        self.assertEqual(pct_28, 2.8)

    def test_greedy_set_cover_overlap_deduplication(self):
        """
        Verify Greedy Set-Cover Token Attribution:
        - Candidate A matches tokens 100..200 (101 tokens)
        - Candidate B matches tokens 150..250 (101 tokens, overlapping with A by 51 tokens)
        - Candidate B must only be attributed the 50 unclaimed tokens (201..250).
        - Total attributed words must equal 101 + 50 = 151 words.
        """
        N = 1000
        cand_a = CandidateSource(
            source_id="src_a",
            source_name="Foundations of Machine Learning",
            source_url="https://doi.org/10.1000/1",
            source_type="Publication",
            spans=[(100, 200)]  # 101 words
        )
        cand_b = CandidateSource(
            source_id="src_b",
            source_name="neuralnetworks.org",
            source_url="https://neuralnetworks.org/primer",
            source_type="Internet",
            spans=[(150, 250)]  # 101 words, overlaps 150..200 (51 words)
        )

        result = calculate_non_overlapping_top_sources(
            total_tokens=N,
            candidate_sources=[cand_a, cand_b],
            min_match_threshold=8
        )

        top_sources = result['top_sources']
        self.assertEqual(len(top_sources), 2)

        src_1 = top_sources[0]
        self.assertEqual(src_1['rank'], 1)
        self.assertEqual(src_1['source_name'], "Foundations of Machine Learning")
        self.assertEqual(src_1['matched_words'], 101)
        self.assertEqual(src_1['similarity_display'], "10%")
        self.assertEqual(src_1['color_theme'], "pink")

        src_2 = top_sources[1]
        self.assertEqual(src_2['rank'], 2)
        self.assertEqual(src_2['source_name'], "neuralnetworks.org")
        # Exactly 50 unclaimed words
        self.assertEqual(src_2['matched_words'], 50)
        self.assertEqual(src_2['similarity_display'], "5%")
        self.assertEqual(src_2['color_theme'], "blue")

        # Guarantee: non-overlapping sum == total attributed words
        self.assertEqual(result['total_attributed_words'], 151)
        self.assertEqual(result['overall_similarity_percentage'], 15.1)
        self.assertEqual(result['overall_similarity_display'], "15%")

    def test_relegation_of_sources_below_threshold(self):
        """
        Verify that a source whose unclaimed word count is below the minimum threshold (e.g. < 8 words)
        is excluded from Top Sources and relegated to overlapping sources.
        """
        N = 1000
        cand_a = CandidateSource(
            source_id="src_a",
            source_name="Major Source",
            source_type="Publication",
            spans=[(10, 100)]  # 91 words
        )
        cand_b = CandidateSource(
            source_id="src_b",
            source_name="Minor Overlapping Source",
            source_type="Internet",
            spans=[(50, 105)]  # 56 words, but only 5 words (101..105) are unclaimed
        )

        result = calculate_non_overlapping_top_sources(
            total_tokens=N,
            candidate_sources=[cand_a, cand_b],
            min_match_threshold=8
        )

        top_sources = result['top_sources']
        self.assertEqual(len(top_sources), 1)
        self.assertEqual(top_sources[0]['source_name'], "Major Source")

        # Source B should be in overlapping_sources
        overlapping = result['overlapping_sources']
        self.assertEqual(len(overlapping), 1)
        self.assertEqual(overlapping[0]['source_name'], "Minor Overlapping Source")
        self.assertEqual(overlapping[0]['unclaimed_words'], 5)

    def test_color_theme_cycling(self):
        """Verify 4-color cycling: 1 -> pink, 2 -> blue, 3 -> teal, 4 -> purple, 5 -> pink."""
        N = 2000
        candidates = [
            CandidateSource(source_id=f"src_{i}", source_name=f"Source {i}", spans=[(i * 100, i * 100 + 50)])
            for i in range(1, 6)
        ]

        result = calculate_non_overlapping_top_sources(N, candidates, min_match_threshold=8)
        top = result['top_sources']
        self.assertEqual(len(top), 5)

        self.assertEqual(top[0]['color_theme'], "pink")
        self.assertEqual(top[1]['color_theme'], "blue")
        self.assertEqual(top[2]['color_theme'], "teal")
        self.assertEqual(top[3]['color_theme'], "purple")
        self.assertEqual(top[4]['color_theme'], "pink")  # cycles back to pink

    def test_output_json_payload_structure(self):
        """Verify structured JSON output payload matches the exact PRD specification."""
        N = 1000
        cand = CandidateSource(
            source_id="pub_1",
            source_name="Dynamic organisational capabilities and employee flourishing in a precarious ...",
            source_url="https://doi.org/10.xxxx/123",
            source_type="Publication",
            spans=[(0, 51)]  # 52 words
        )

        result = calculate_non_overlapping_top_sources(N, [cand], min_match_threshold=8)

        # Header structure
        header = result['top_sources_header']
        self.assertEqual(header['title'], "Top Sources")
        self.assertEqual(
            header['description'],
            "The sources with the highest number of matches within the submission. Overlapping sources will not be displayed."
        )

        # Top source fields
        self.assertEqual(len(result['top_sources']), 1)
        s = result['top_sources'][0]
        self.assertEqual(s['rank'], 1)
        self.assertEqual(s['source_type'], "Publication")
        self.assertEqual(s['source_name'], "Dynamic organisational capabilities and employee flourishing in a precarious ...")
        self.assertEqual(s['source_url'], "https://doi.org/10.xxxx/123")
        self.assertEqual(s['matched_words'], 52)
        self.assertEqual(s['similarity_display'], "5%")
        self.assertEqual(s['color_theme'], "pink")

    def test_integration_with_criteria_and_academic_scorer(self):
        """Integration test: Verify compute_report_criteria produces top_sources_header and theme keys."""
        institution = Institution.objects.create(name="Integrity Institute", short_name="II", domain="ii.edu")
        user = User.objects.create_user(username="prof_top_sources", email="prof@ii.edu", password="pw", institution=institution)
        doc = Document.objects.create(title="Top Sources Integration Doc", uploaded_by=user, word_count=500)
        report = SimilarityReport.objects.create(
            document=doc,
            status=SimilarityReport.Status.COMPLETED,
            overall_similarity=12.0,
            matched_words=60,
            total_words=500,
            source_breakdown=[
                {
                    'source_name': 'Journal of Academic Computing',
                    'source_type': 'Publication',
                    'source_url': 'https://doi.org/10.1000/1',
                    'matched_words': 40,
                    'similarity_display': '8%',
                    'percentage': 8.0,
                    'color_theme': 'pink'
                },
                {
                    'source_name': 'sajhrm.co.za',
                    'source_type': 'Internet',
                    'source_url': 'https://sajhrm.co.za/index.php/sajhrm',
                    'matched_words': 20,
                    'similarity_display': '4%',
                    'percentage': 4.0,
                    'color_theme': 'blue'
                }
            ]
        )

        criteria = compute_report_criteria(report)

        self.assertIn('top_sources_header', criteria)
        self.assertEqual(criteria['top_sources_header']['title'], "Top Sources")
        self.assertIn("Overlapping sources will not be displayed", criteria['top_sources_header']['description'])

        top_sources = criteria['top_sources']
        self.assertEqual(len(top_sources), 2)

        first = top_sources[0]
        self.assertEqual(first['rank'], 1)
        self.assertEqual(first['source_name'], "Journal of Academic Computing")
        self.assertEqual(first['source_type'], "Publication")
        self.assertEqual(first['color_theme'], "pink")
        self.assertEqual(first['similarity_display'], "8%")

        second = top_sources[1]
        self.assertEqual(second['rank'], 2)
        self.assertEqual(second['source_name'], "sajhrm.co.za")
        self.assertEqual(second['source_type'], "Internet")
        self.assertEqual(second['color_theme'], "blue")
        self.assertEqual(second['similarity_display'], "4%")
