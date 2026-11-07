"""
Turnitin-Style Plagiarism Detection & Top Sources Aggregation Engine Runner.
============================================================================
Executes an end-to-end live demonstration of the 6-stage pipeline:
1. Document Ingestion (.pdf, .docx, .txt, or raw text)
2. Bilingual Normalization (English + Hindi Devanagari)
3. Winnowing Fingerprinting (k=7, w=5) & Inverted Index Matching
4. Exclusion Filters (Bibliography, Quotes, Citations)
5. Greedy Weighted Set-Cover (Non-Overlapping Top Sources Attribution)
6. Turnitin Structured JSON Report Output
"""

import sys
import json
from analysis.plagiarism_engine import PlagiarismDetectionEngine

# Reconfigure stdout to UTF-8 for Devanagari character display in console
sys.stdout.reconfigure(encoding='utf-8')


def main():
    print("=" * 80)
    print("PROOVEXA INDUSTRIAL PLAGIARISM DETECTION & TOP SOURCES ENGINE")
    print("Modeled after Turnitin | Bilingual: English & Hindi (Devanagari)")
    print("=" * 80)

    # 1. Initialize Engine with Turnitin-grade parameters
    engine = PlagiarismDetectionEngine(
        k_shingle_size=7,
        window_size=5,
        min_match_words=8,
        exclude_bibliography=True,
        exclude_quotations=True,
        exclude_citations=True
    )

    # 2. Reference Corpus (Internet Web Crawl, Academic Publications, Student Papers)
    reference_corpus = [
        {
            "id": "src_001",
            "name": "www.mdpi.com",
            "type": "Internet",
            "url": "https://www.mdpi.com/journal/religions/article/7821",
            "text": (
                "In this study, pragmatism is the approach that will be used to explore how qualitative "
                "methodologies intersect with modern information retrieval, semantic analysis, and empirical data collection."
            ),
        },
        {
            "id": "src_002",
            "name": "coursehero.com",
            "type": "Internet",
            "url": "https://www.coursehero.com/file/99214/pragmatism-study/",
            "text": (
                # 100% overlapping with Source 1 (MDPI) — must be eliminated by Greedy Set-Cover!
                "pragmatism is the approach that will be used to explore how qualitative methodologies intersect"
            ),
        },
        {
            "id": "src_003",
            "name": "journal1.uad.ac.id",
            "type": "Publication",
            "url": "https://journal1.uad.ac.id/index.php/article/456",
            "text": (
                "प्राकृतिक भाषा प्रसंस्करण में शब्द विभाजन और विलोपन तकनीकों का गहन अध्ययन किया गया है "
                "जिसमें देवनागरी लिपि के विशिष्ट चिह्नों और मात्राओं का मानकीकरण आवश्यक है।"
            ),
        },
        {
            "id": "src_004",
            "name": "metropolitan.edu/repository/theses/2025/nlp",
            "type": "Submitted works",
            "url": "https://metropolitan.edu/repository/theses/2025/nlp",
            "text": (
                "supervised machine learning algorithms classify syntactic structures using recurrent gate operations "
                "and gradient descent optimizations across neural tensor manifolds."
            ),
        },
    ]

    print(f"\n[+] Indexing Reference Corpus ({len(reference_corpus)} multi-domain sources)...")
    engine.index_corpus(reference_corpus)
    print(f"    Indexed {len(engine.inverted_index.index):,} unique winnowed shingle fingerprints.")

    # 3. Submitted Manuscript with English, Hindi, Direct Quotes, Citations, and References
    submitted_manuscript = """A Comparative Inquiry into Computational Linguistics and Information Retrieval Systems

In this study, pragmatism is the approach that will be used to explore how qualitative methodologies intersect with modern information retrieval, semantic analysis, and empirical data collection.

इसके अतिरिक्त, प्राकृतिक भाषा प्रसंस्करण में शब्द विभाजन और विलोपन तकनीकों का गहन अध्ययन किया गया है जिसमें देवनागरी लिपि के विशिष्ट चिह्नों और मात्राओं का मानकीकरण आवश्यक है।

Furthermore, supervised machine learning algorithms classify syntactic structures using recurrent gate operations and gradient descent optimizations across neural tensor manifolds.

According to Dr. Alan Smith, "quoted passages enclosed in double quotation marks should be automatically excluded from plagiarism metrics" (Smith et al., 2024).

Earlier research also affirmed this methodology (शर्मा, 2021).

References:
1. Smith, A., Doe, J., and Kumar, R. (2024). Advanced Information Retrieval. Oxford University Press.
2. शर्मा, आर. (२०२१). हिंदी भाषा और कंप्यूटिंग. वाणी प्रकाशन.
3. MDPI Academic Research (2025). Pragmatism in NLP.
"""

    print("\n[+] Analyzing Submitted Manuscript (English + Hindi Devanagari)...")
    print(f"    Submission Size: {len(submitted_manuscript.split())} words, {len(submitted_manuscript)} characters.")

    report_payload = engine.analyze(
        document=submitted_manuscript,
        filename="thesis_submission.docx",
        submission_id="trn:oid:::3971:157542951"
    )

    print("\n" + "=" * 80)
    print("TURNITIN-STYLE STRUCTURED ORIGINALITY REPORT PAYLOAD (JSON)")
    print("=" * 80)
    print(json.dumps(report_payload, indent=2, ensure_ascii=False))

    print("\n" + "=" * 80)
    print("EXECUTIVE SUMMARY & GREEDY SET-COVER VALIDATION")
    print("=" * 80)
    details = report_payload["submission_details"]
    overview = report_payload["integrity_overview"]

    print(f"Submission ID:       {details['submission_id']}")
    print(f"Filename:            {details['filename']}")
    print(f"Language Detected:   {details['language_detected']}")
    print(f"Word Count:          {details['word_count']} words")
    print(f"Overall Similarity:  {overview['overall_similarity_percent']}%")

    print("\n--- DATABASE SOURCE BREAKDOWN ---")
    sb = overview["source_breakdown"]
    print(f"  Internet Sources:  {sb['internet_percent']}%")
    print(f"  Publications:      {sb['publications_percent']}%")
    print(f"  Submitted Works:   {sb['submitted_works_percent']}%")

    print("\n--- MATCH GROUPS (TURNITIN CLASSIFICATION) ---")
    mg = overview["match_groups"]
    print(f"  Not Cited or Quoted:   {mg['not_cited_or_quoted_percent']}%")
    print(f"  Missing Quotations:    {mg['missing_quotations_percent']}%")
    print(f"  Missing Citation:      {mg['missing_citation_percent']}%")
    print(f"  Cited and Quoted:      {mg['cited_and_quoted_percent']}%")

    print("\n--- ATTRIBUTED TOP SOURCES (NON-OVERLAPPING) ---")
    for s in report_payload["top_sources"]:
        print(f"  Rank #{s['rank']}: {s['source_name']} ({s['source_type']}) - {s['similarity_percent']}% ({s['matched_word_count']} unique words)")

    print("\n--- NON-OVERLAPPING HIGHLIGHTED SPANS ---")
    for span in report_payload["annotated_document_spans"]:
        snippet = span["text_snippet"].replace("\n", " ")
        if len(snippet) > 70:
            snippet = snippet[:67] + "..."
        print(f"  Span #{span['span_id']} [Source #{span['source_rank']}]: \"{snippet}\"")
        print(f"    Offsets: [{span['start_char']}:{span['end_char']}] | Classification: {span['classification']}")

    print("\n[✓] Overlapping Sources Check:")
    top_source_names = [s["source_name"] for s in report_payload["top_sources"]]
    if "coursehero.com" not in top_source_names:
        print("    PASS: Secondary source 'coursehero.com' (100% overlapping with MDPI) was successfully eliminated!")
        print("          Double-counting strictly prevented.")
    else:
        print("    FAIL: Overlapping source was not eliminated.")

    print("\n[✓] Mathematical Integrity Check:")
    db_sum = sb['internet_percent'] + sb['publications_percent'] + sb['submitted_works_percent']
    mg_sum = (mg['not_cited_or_quoted_percent'] + mg['missing_quotations_percent'] +
              mg['missing_citation_percent'] + mg['cited_and_quoted_percent'])
    if db_sum == overview['overall_similarity_percent'] and mg_sum == overview['overall_similarity_percent']:
        print(f"    PASS: Database sum ({db_sum}%) and Match Groups sum ({mg_sum}%) equal Overall Similarity ({overview['overall_similarity_percent']}%).")

    print("=" * 80)


if __name__ == '__main__':
    main()
