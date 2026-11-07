"""
Comprehensive Test Suite for Plagiarism Detection & Top Sources Aggregation Engine.
===================================================================================
Tests all 6 pipeline stages and technical specifications:
1. Ingestion: PDF, DOCX (with tables), and multi-encoding TXT.
2. Bilingual Normalization: NFKC, Nukta unification, ZWJ/ZWNJ invariant hashes,
   Devanagari Halant/Matra binding, and language detection (en-IN, hi-IN, mixed).
3. Exclusion Filters: English & Hindi bibliography headers, quotes, and in-text citations.
4. Winnowing: k=7, w=5, 64-bit rolling hashes, anchor coalescing, inverted index.
5. Top Sources Resolution: Greedy Set-Cover, non-overlapping source attribution,
   elimination of 100% overlapping secondary sources, '<1%' threshold formatting.
6. JSON Schema: Exact compliance with Turnitin report payload.
"""

import os
import io
import json
import unittest
import unicodedata

from analysis.plagiarism_engine import (
    PlagiarismDetectionEngine,
    DocumentParser,
    BilingualPreprocessor,
    WinnowingFingerprinter,
    InvertedCorpusIndex,
    ExclusionFiltersEngine,
    TopSourcesResolver,
    PlagiarismReportGenerator,
)


class TestPlagiarismDetectionEngine(unittest.TestCase):

    def setUp(self):
        self.engine = PlagiarismDetectionEngine(
            k_shingle_size=7,
            window_size=5,
            min_match_words=8,
            exclude_bibliography=True,
            exclude_quotations=True,
            exclude_citations=True
        )
        self.preprocessor = BilingualPreprocessor()

    # -------------------------------------------------------------------------
    # 1. Ingestion & Multi-Format Parsing Tests
    # -------------------------------------------------------------------------
    def test_txt_encoding_auto_detection(self):
        """Test universal encoding auto-detection for UTF-8, UTF-16, and Latin-1."""
        raw_text = "This is an academic research document analyzing information retrieval algorithms."

        # UTF-8 with BOM
        utf8_bom_bytes = raw_text.encode('utf-8-sig')
        doc1 = DocumentParser.parse(utf8_bom_bytes, filename="utf8_bom.txt")
        self.assertEqual(doc1.file_type, "txt")
        self.assertIn("academic research", doc1.full_text)

        # UTF-16
        utf16_bytes = raw_text.encode('utf-16')
        doc2 = DocumentParser.parse(utf16_bytes, filename="utf16.txt")
        self.assertIn("academic research", doc2.full_text)

        # ISO-8859-1 (Latin-1) with accented characters
        latin1_text = "Café standard evaluation for academic résumé."
        latin1_bytes = latin1_text.encode('iso-8859-1')
        doc3 = DocumentParser.parse(latin1_bytes, filename="latin1.txt")
        self.assertIn("Café", doc3.full_text)

    def test_docx_parsing_with_tables_and_breaks(self):
        """Test DOCX parsing extracting paragraphs, table cells, and page breaks."""
        import docx
        doc_obj = docx.Document()
        doc_obj.add_heading("Algorithmic Complexity in NLP", level=1)
        doc_obj.add_paragraph("Information retrieval engines rely on robust inverted indexes.")

        # Add a table
        table = doc_obj.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "Metric"
        table.cell(0, 1).text = "Value"
        table.cell(1, 0).text = "Precision"
        table.cell(1, 1).text = "0.95"

        doc_obj.add_paragraph("Conclusion of the introductory section.")

        buffer = io.BytesIO()
        doc_obj.save(buffer)
        docx_bytes = buffer.getvalue()

        parsed = DocumentParser.parse(docx_bytes, filename="test_doc.docx")
        self.assertEqual(parsed.file_type, "docx")
        self.assertIn("Information retrieval engines", parsed.full_text)
        self.assertIn("Precision | 0.95", parsed.full_text)
        self.assertGreater(parsed.word_count, 10)

    def test_pdf_parsing_layout_aware(self):
        """Test PDF parsing using PyMuPDF stream extraction."""
        import fitz
        pdf_doc = fitz.open()
        page = pdf_doc.new_page(width=612, height=792)
        rect = fitz.Rect(50, 50, 500, 200)
        page.insert_textbox(rect, "Turnitin originality analysis evaluates non-overlapping sources.")
        pdf_bytes = pdf_doc.write()
        pdf_doc.close()

        parsed = DocumentParser.parse(pdf_bytes, filename="sample.pdf")
        self.assertEqual(parsed.file_type, "pdf")
        self.assertIn("Turnitin originality analysis", parsed.full_text)
        self.assertEqual(parsed.page_count, 1)

    # -------------------------------------------------------------------------
    # 2. Bilingual Normalization & Devanagari Specifics
    # -------------------------------------------------------------------------
    def test_hindi_nukta_canonical_unification(self):
        """Test that decomposed and precomposed Nukta characters normalize to identical tokens."""
        # Decomposed: ज + ़ vs Precomposed: ज़
        decomposed_za = "ज\u093cिंदगी"
        precomposed_za = "ज़िंदगी"

        norm_dec = self.preprocessor.normalize_word_token(decomposed_za)
        norm_pre = self.preprocessor.normalize_word_token(precomposed_za)
        self.assertEqual(norm_dec, norm_pre)

        # Decomposed: फ + ़ vs Precomposed: फ़ (both syllables)
        decomposed_fa = "फ\u093cलसफ\u093cा"
        precomposed_fa = "फ़लसफ़ा"
        self.assertEqual(
            self.preprocessor.normalize_word_token(decomposed_fa),
            self.preprocessor.normalize_word_token(precomposed_fa)
        )

    def test_devanagari_halant_and_matra_conjunct_binding(self):
        """Test that words with Halant (\u094D) and Matras are preserved as unified tokens."""
        hindi_text = "दृष्टिकोण और प्रणाली का विश्लेषण अत्यंत महत्वपूर्ण है।"
        tokens = self.preprocessor.tokenize_with_offsets(hindi_text)
        token_words = [t.original_word for t in tokens]

        # Ensure Halant conjuncts are NOT split:
        self.assertIn("दृष्टिकोण", token_words)
        self.assertIn("प्रणाली", token_words)
        self.assertIn("विश्लेषण", token_words)
        self.assertIn("महत्वपूर्ण", token_words)

        # Verify character coordinates point to exact slices in original text
        for t in tokens:
            self.assertEqual(hindi_text[t.start_char:t.end_char], t.original_word)

    def test_zwnj_and_zwj_invariant_hash_with_exact_offset_retention(self):
        """Test that ZWNJ (\u200C) and ZWJ (\u200D) are stripped for hashes but offsets point to raw text."""
        raw_text_with_zwnj = "प्राकृतिक भाषा\u200c प्रसंस्करण"
        tokens = self.preprocessor.tokenize_with_offsets(raw_text_with_zwnj)

        # The token covering 'भाषा\u200c' should have stripped normalized word 'भाषा'
        # but its start_char and end_char must include the ZWNJ character
        zwnj_token = [t for t in tokens if "भाषा" in t.original_word][0]
        self.assertIn("\u200c", zwnj_token.original_word)
        self.assertNotIn("\u200c", zwnj_token.normalized_word)
        self.assertEqual(raw_text_with_zwnj[zwnj_token.start_char:zwnj_token.end_char], zwnj_token.original_word)

    def test_language_detection(self):
        """Test language detection for English, Hindi, and mixed documents."""
        en_text = "Distributed computing and hash tables provide rapid similarity detection."
        hi_text = "कृत्रिम बुद्धिमत्ता और मशीन लर्निंग शैक्षणिक अनुसंधान में सहायक हैं।"
        mixed_text = "This research evaluates प्राकृतिक भाषा प्रसंस्करण in Indian languages."

        self.assertEqual(self.preprocessor.detect_language(en_text), "en-IN")
        self.assertEqual(self.preprocessor.detect_language(hi_text), "hi-IN")
        self.assertEqual(self.preprocessor.detect_language(mixed_text), "mixed")

    # -------------------------------------------------------------------------
    # 3. Exclusion Filters Engine (Bibliography, Quotes, Citations)
    # -------------------------------------------------------------------------
    def test_english_and_hindi_bibliography_exclusion(self):
        """Test detection and exclusion of terminal references in English and Hindi."""
        ex_engine = ExclusionFiltersEngine(exclude_bibliography=True)

        # English bibliography
        doc_en = (
            "This is the core body of the academic thesis covering experimental methodology.\n\n"
            "References:\n"
            "1. Smith, J. (2024). Plagiarism Systems. Springer.\n"
            "2. Doe, A. (2023). Winnowing Algorithms."
        )
        ex_en = ex_engine.detect_bibliography_regions(doc_en)
        self.assertEqual(len(ex_en), 1)
        self.assertEqual(ex_en[0].reason, "bibliography")
        self.assertIn("References", doc_en[ex_en[0].start_char:ex_en[0].end_char])

        # Hindi bibliography (संदर्भ ग्रंथ सूची)
        doc_hi = (
            "शोध प्रबंध का मुख्य भाग यहाँ विस्तृत रूप से वर्णित किया गया है।\n\n"
            "संदर्भ ग्रंथ सूची:\n"
            "१. शर्मा, आर. (२०२१). हिंदी भाषा और कंप्यूटिंग.\n"
            "२. गुप्ता, एस. (२०१९). प्राकृतिक भाषा प्रसंस्करण."
        )
        ex_hi = ex_engine.detect_bibliography_regions(doc_hi)
        self.assertEqual(len(ex_hi), 1)
        self.assertEqual(ex_hi[0].reason, "bibliography")
        self.assertIn("संदर्भ ग्रंथ सूची", doc_hi[ex_hi[0].start_char:ex_hi[0].end_char])

    def test_quotations_and_citations_detection(self):
        """Test detection of quotations and in-text citations in English and Hindi."""
        ex_engine = ExclusionFiltersEngine(exclude_quotations=True, exclude_citations=True)
        sample = (
            'According to prior studies, "machine learning algorithms detect text similarity" (Smith et al., 2024). '
            'Also seen in earlier work (शर्मा, 2021) and [1, 2].'
        )

        quotes = ex_engine.detect_quotation_regions(sample)
        self.assertEqual(len(quotes), 1)
        self.assertIn("machine learning algorithms detect text similarity", quotes[0].matched_text)

        citations = ex_engine.detect_citation_regions(sample)
        # Should detect (Smith et al., 2024), (शर्मा, 2021), and [1, 2]
        self.assertGreaterEqual(len(citations), 3)

    def test_match_groups_classification(self):
        """Test classification into Turnitin 4 Match Groups."""
        ex_engine = ExclusionFiltersEngine()

        # 1. Cited and quoted: "text" (Smith, 2024)
        s1 = 'The author stated "data structures are essential for scaling" (Smith, 2024).'
        start1 = s1.find('"data structures')
        end1 = s1.find('scaling"') + 8
        self.assertEqual(ex_engine.classify_match_span(start1, end1, s1), "cited_and_quoted")

        # 2. Missing quotations: data structures are essential (Smith, 2024) [no quotes]
        s2 = "Data structures are essential for scaling in systems (Smith, 2024)."
        start2 = 0
        end2 = s2.find("systems") + 7
        self.assertEqual(ex_engine.classify_match_span(start2, end2, s2), "missing_quotations")

        # 3. Missing citation: "data structures are essential" [no citation]
        s3 = 'The author stated "data structures are essential for scaling".'
        start3 = s3.find('"data structures')
        end3 = s3.find('scaling"') + 8
        self.assertEqual(ex_engine.classify_match_span(start3, end3, s3), "missing_citation")

        # 4. Not cited or quoted
        s4 = "Data structures are essential for scaling without any attribution whatsoever."
        self.assertEqual(ex_engine.classify_match_span(0, 30, s4), "not_cited_or_quoted")

    # -------------------------------------------------------------------------
    # 4. Winnowing Fingerprinting & Inverted Index Tests
    # -------------------------------------------------------------------------
    def test_winnowing_guarantee_and_invariance(self):
        """Test that winnowing detects any identical sequence >= t = w + k - 1."""
        wp = WinnowingFingerprinter(k=7, w=5)
        text_a = "deep neural networks utilize backpropagation and gradient descent optimization algorithms to minimize loss functions"
        text_b = "In this research deep neural networks utilize backpropagation and gradient descent optimization algorithms to minimize loss functions across layers"

        toks_a = self.preprocessor.tokenize_with_offsets(text_a)
        toks_b = self.preprocessor.tokenize_with_offsets(text_b)

        fps_a = wp.compute_fingerprints(toks_a)
        fps_b = wp.compute_fingerprints(toks_b)

        hashes_a = {fp.hash_val for fp in fps_a}
        hashes_b = {fp.hash_val for fp in fps_b}

        # They must share winnowed fingerprints because the shared sequence is 14 words (> t=11)
        shared = hashes_a.intersection(hashes_b)
        self.assertGreater(len(shared), 0)

    # -------------------------------------------------------------------------
    # 5. Greedy Weighted Set Cover Top Sources Resolution Tests
    # -------------------------------------------------------------------------
    def test_greedy_attribution_eliminating_overlapping_sources(self):
        """
        Validate the user's exact specification walkthrough:
        - Source 1 (MDPI) covers 10 words.
        - Source 2 (Course Hero) covers 6 words (which completely overlap with Source 1).
        - Source 3 (Journal X) covers 4 separate words.
        Greedy Set-Cover must assign Source 1 as Top Source #1.
        Source 2 must have 0 unique contribution and be DROPPED from Top Sources!
        """
        resolver = TopSourcesResolver(min_continuous_words=3)

        # 14 words total
        submission_text = (
            "apple banana cherry date elderberry fig grape honeydew kiwi lemon mango orange papaya quince"
        )
        tokens = self.preprocessor.tokenize_with_offsets(submission_text)
        total_words = len(tokens)
        self.assertEqual(total_words, 14)

        from analysis.plagiarism_engine.fingerprinting import RawMatch

        # Match 1: Source A covers words 0..9 (10 words)
        m_a = RawMatch(
            span_id=1,
            source_id="src_mdpi",
            source_name="www.mdpi.com",
            source_type="Internet",
            source_url="https://www.mdpi.com/article/1",
            sub_token_start=0,
            sub_token_end=9,
            sub_start_char=tokens[0].start_char,
            sub_end_char=tokens[9].end_char,
            src_token_start=0,
            src_token_end=9,
            src_start_char=0,
            src_end_char=100,
            matched_text=submission_text[tokens[0].start_char:tokens[9].end_char],
            token_count=10,
        )

        # Match 2: Source B covers words 2..7 (6 words, 100% inside Source A's span)
        m_b = RawMatch(
            span_id=2,
            source_id="src_coursehero",
            source_name="www.coursehero.com",
            source_type="Internet",
            source_url="https://www.coursehero.com/doc/2",
            sub_token_start=2,
            sub_token_end=7,
            sub_start_char=tokens[2].start_char,
            sub_end_char=tokens[7].end_char,
            src_token_start=0,
            src_token_end=5,
            src_start_char=0,
            src_end_char=60,
            matched_text=submission_text[tokens[2].start_char:tokens[7].end_char],
            token_count=6,
        )

        # Match 3: Source C covers words 10..13 (4 words, disjoint)
        m_c = RawMatch(
            span_id=3,
            source_id="src_journal",
            source_name="journal1.uad.ac.id",
            source_type="Publication",
            source_url="https://journal1.uad.ac.id/paper/3",
            sub_token_start=10,
            sub_token_end=13,
            sub_start_char=tokens[10].start_char,
            sub_end_char=tokens[13].end_char,
            src_token_start=0,
            src_token_end=3,
            src_start_char=0,
            src_end_char=40,
            matched_text=submission_text[tokens[10].start_char:tokens[13].end_char],
            token_count=4,
        )

        raw_matches = [m_a, m_b, m_c]

        top_sources, annotated_spans, claimed_tokens = resolver.resolve(
            raw_matches=raw_matches,
            tokens=tokens,
            full_text=submission_text,
            total_words=total_words,
        )

        # Source A is Rank 1 with 10 words
        self.assertEqual(len(top_sources), 2)  # Source B was dropped!
        self.assertEqual(top_sources[0].source_id, "src_mdpi")
        self.assertEqual(top_sources[0].rank, 1)
        self.assertEqual(top_sources[0].matched_word_count, 10)

        # Source C is Rank 2 with 4 words
        self.assertEqual(top_sources[1].source_id, "src_journal")
        self.assertEqual(top_sources[1].rank, 2)
        self.assertEqual(top_sources[1].matched_word_count, 4)

        # Verify Source B was NOT double-counted
        source_ids_in_top = [s.source_id for s in top_sources]
        self.assertNotIn("src_coursehero", source_ids_in_top)

        # Verify total claimed words = 10 + 4 = 14 (100% of document, no overlapping double counting)
        self.assertEqual(len(claimed_tokens), 14)

    def test_similarity_percent_formatting_less_than_one(self):
        """Test that similarity < 1% displays '<1%' string."""
        resolver = TopSourcesResolver(min_continuous_words=3)
        tokens = [None] * 1000  # 1000 words document
        from analysis.plagiarism_engine.fingerprinting import RawMatch

        raw_match = RawMatch(
            span_id=1,
            source_id="src_tiny",
            source_name="example.com",
            source_type="Internet",
            source_url="http://example.com",
            sub_token_start=0,
            sub_token_end=4,  # 5 words out of 1000 = 0.5% (< 1%)
            sub_start_char=0,
            sub_end_char=25,
            src_token_start=0,
            src_token_end=4,
            src_start_char=0,
            src_end_char=25,
            matched_text="word word word word word",
            token_count=5,
        )
        mock_tokens = [
            type("MockToken", (), {"token_index": i, "start_char": i * 5, "end_char": i * 5 + 4})()
            for i in range(10)
        ]

        top_sources, _, _ = resolver.resolve(
            raw_matches=[raw_match],
            tokens=mock_tokens,
            full_text="word word word word word",
            total_words=1000,
        )
        self.assertEqual(len(top_sources), 1)
        self.assertEqual(top_sources[0].similarity_percent, "<1%")

    # -------------------------------------------------------------------------
    # 6. End-to-End Analysis & Turnitin JSON Schema Validation
    # -------------------------------------------------------------------------
    def test_end_to_end_bilingual_plagiarism_analysis(self):
        """
        Full end-to-end pipeline test with Hindi and English text,
        indexing candidate corpus, exclusions, top sources resolution,
        and validating the exact JSON schema required by Turnitin.
        """
        candidate_corpus = [
            {
                "id": "src_001",
                "name": "www.mdpi.com",
                "type": "Internet",
                "url": "https://www.mdpi.com/journal/religions/123",
                "text": (
                    "In this study, pragmatism is the approach that will be used to explore how qualitative "
                    "methodologies intersect with modern information retrieval and empirical data collection."
                ),
            },
            {
                "id": "src_002",
                "name": "journal1.uad.ac.id",
                "type": "Internet",
                "url": "https://journal1.uad.ac.id/index.php/article/456",
                "text": (
                    "प्राकृतिक भाषा प्रसंस्करण में शब्द विभाजन और विलोपन तकनीकों का गहन अध्ययन किया गया है।"
                ),
            },
        ]

        submitted_document = (
            "Title: Pragmatism and Multilingual NLP Systems\n\n"
            "In this study, pragmatism is the approach that will be used to explore how qualitative "
            "methodologies intersect with modern information retrieval and empirical data collection.\n\n"
            "इसके अतिरिक्त, प्राकृतिक भाषा प्रसंस्करण में शब्द विभाजन और विलोपन तकनीकों का गहन अध्ययन किया गया है।\n\n"
            'According to Dr. Alan, "quoted text should not be penalized when excluded" (Alan, 2023).\n\n'
            "References:\n"
            "1. Alan, D. (2023). Ethics in IR. Oxford Press.\n"
            "2. MDPI Academic Research (2024).\n"
        )

        engine = PlagiarismDetectionEngine(
            k_shingle_size=7,
            window_size=5,
            min_match_words=8,
            exclude_bibliography=True,
            exclude_quotations=True,
            exclude_citations=True
        )

        report = engine.analyze(
            document=submitted_document,
            candidate_sources=candidate_corpus,
            filename="thesis_submission.docx",
            submission_id="trn:oid:::3971:157542951"
        )

        # Validate Schema Structure
        self.assertIn("submission_details", report)
        self.assertIn("integrity_overview", report)
        self.assertIn("top_sources", report)
        self.assertIn("annotated_document_spans", report)

        sub_details = report["submission_details"]
        self.assertEqual(sub_details["submission_id"], "trn:oid:::3971:157542951")
        self.assertEqual(sub_details["filename"], "thesis_submission.docx")
        self.assertIn(sub_details["language_detected"], ["en-IN", "hi-IN", "mixed"])
        self.assertGreater(sub_details["word_count"], 0)
        self.assertGreater(sub_details["char_count"], 0)

        overview = report["integrity_overview"]
        self.assertIn("overall_similarity_percent", overview)
        self.assertIn("source_breakdown", overview)
        self.assertIn("filters_applied", overview)
        self.assertIn("match_groups", overview)

        # Filters applied check
        self.assertTrue(overview["filters_applied"]["bibliography_excluded"])
        self.assertTrue(overview["filters_applied"]["quotes_excluded"])
        self.assertTrue(overview["filters_applied"]["citations_excluded"])

        # Check Top Sources
        self.assertIsInstance(report["top_sources"], list)
        self.assertGreater(len(report["top_sources"]), 0)
        top1 = report["top_sources"][0]
        self.assertEqual(top1["rank"], 1)
        self.assertIn("source_id", top1)
        self.assertIn("source_name", top1)
        self.assertIn("source_type", top1)
        self.assertIn("similarity_percent", top1)
        self.assertIn("matched_word_count", top1)

        # Check Annotated Document Spans
        self.assertIsInstance(report["annotated_document_spans"], list)
        self.assertGreater(len(report["annotated_document_spans"]), 0)
        span1 = report["annotated_document_spans"][0]
        self.assertIn("span_id", span1)
        self.assertIn("source_rank", span1)
        self.assertIn("start_char", span1)
        self.assertIn("end_char", span1)
        self.assertIn("text_snippet", span1)
        self.assertIn("source_url", span1)
        self.assertIn("classification", span1)

        # Pretty-print sample JSON report for inspection
        json_output = json.dumps(report, indent=2, ensure_ascii=False)
        self.assertIn("trn:oid:::3971:157542951", json_output)

    def test_toggleable_filters_effect_on_scoring(self):
        """Test that turning off exclusion filters allows matching inside quotes/bibliography."""
        quoted_text = '"This is a direct verbatim quotation that should only be flagged when quotes are included in score."'
        source_text = "This is a direct verbatim quotation that should only be flagged when quotes are included in score."

        candidate = [{
            "id": "src_quote",
            "name": "Quotation Source",
            "type": "Internet",
            "text": source_text
        }]

        # 1. When quotes are excluded (default: True)
        engine_excl = PlagiarismDetectionEngine(min_match_words=5, exclude_quotations=True)
        rep1 = engine_excl.analyze(quoted_text, candidate_sources=candidate)
        self.assertEqual(len(rep1["top_sources"]), 0)
        self.assertEqual(rep1["integrity_overview"]["overall_similarity_percent"], 0)

        # 2. When quotes are included (exclude_quotations = False)
        engine_incl = PlagiarismDetectionEngine(min_match_words=5, exclude_quotations=False)
        rep2 = engine_incl.analyze(quoted_text, candidate_sources=candidate)
        self.assertGreater(len(rep2["top_sources"]), 0)
        self.assertGreater(rep2["integrity_overview"]["overall_similarity_percent"], 50)

    def test_hindi_bibliography_heading_variants(self):
        """Test detection across all required Hindi bibliographic headers."""
        ex_engine = ExclusionFiltersEngine(exclude_bibliography=True)
        headers = [
            "संदर्भ सूची:",
            "ग्रंथसूची:",
            "हवाले:",
            "संदर्भ ग्रंथ:",
            "संदर्भित साहित्य:",
            "संदर्भ ग्रंथ सूची:",
            "संदर्भ:"
        ]

        for h in headers:
            doc = f"यह मुख्य शोध पत्र का महत्वपूर्ण अध्याय है जिसमें विभिन्न सिद्धांतों की समीक्षा की गई है।\n\n{h}\n१. लेखक, ए. (२०२४). पुस्तक."
            regions = ex_engine.detect_bibliography_regions(doc)
            self.assertGreaterEqual(len(regions), 1, f"Failed to detect Hindi bibliography header: {h}")
            self.assertEqual(regions[0].reason, "bibliography")

    def test_mathematical_percentage_sum_invariants(self):
        """
        Verify that:
        1. internet_percent + publications_percent + submitted_works_percent == overall_similarity_percent
        2. not_cited_or_quoted_percent + missing_quotations_percent + missing_citation_percent + cited_and_quoted_percent == overall_similarity_percent
        """
        candidate_corpus = [
            {
                "id": "src_net",
                "name": "Web Source",
                "type": "Internet",
                "text": "artificial intelligence models require extensive dataset curation and validation protocols",
            },
            {
                "id": "src_pub",
                "name": "Academic Publication",
                "type": "Publication",
                "text": "supervised learning classifiers optimize empirical risk minimization across continuous loss functions",
            },
            {
                "id": "src_stu",
                "name": "Student Repository",
                "type": "Submitted works",
                "text": "reinforcement learning agents explore discrete state action spaces using temporal difference updates",
            },
        ]

        submitted = (
            "Introduction to computational machine learning.\n\n"
            "artificial intelligence models require extensive dataset curation and validation protocols.\n\n"
            "supervised learning classifiers optimize empirical risk minimization across continuous loss functions.\n\n"
            "reinforcement learning agents explore discrete state action spaces using temporal difference updates.\n\n"
            "Final conclusion and summary remarks of this paper."
        )

        engine = PlagiarismDetectionEngine(min_match_words=6)
        report = engine.analyze(submitted, candidate_sources=candidate_corpus)

        overview = report["integrity_overview"]
        overall = overview["overall_similarity_percent"]

        # 1. Source breakdown invariant
        sb = overview["source_breakdown"]
        total_sources_pct = sb["internet_percent"] + sb["publications_percent"] + sb["submitted_works_percent"]
        self.assertEqual(total_sources_pct, overall)

        # 2. Match groups invariant
        mg = overview["match_groups"]
        total_mg_pct = (
            mg["not_cited_or_quoted_percent"]
            + mg["missing_quotations_percent"]
            + mg["missing_citation_percent"]
            + mg["cited_and_quoted_percent"]
        )
        self.assertEqual(total_mg_pct, overall)


if __name__ == '__main__':
    unittest.main()
