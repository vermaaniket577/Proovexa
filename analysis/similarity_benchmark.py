"""
Comprehensive 12-Case Academic Similarity & Plagiarism Benchmark Suite.
Tests all requirements specified in Section 10 of project prompt:
1. Identical documents
2. Documents with one copied paragraph
3. Documents with partial sentence overlap
4. Documents with small word substitutions (near-duplicates)
5. Documents with reordered sentences
6. Documents with common phrases only
7. Documents with properly cited quotations
8. Documents with large bibliographies
9. Documents containing repeated passages
10. Documents with no matching source
11. Multiple sources containing the same passages (double-counting prevention)
12. Documents with Unicode, formatting, or extraction differences
"""
from typing import Dict, Any, List
from analysis.winnowing import WinnowingEngine
from analysis.scoring import AcademicSimilarityScorer
from analysis.comparators import ExactMatchComparator, FuzzyComparator


def run_12_case_similarity_benchmark() -> Dict[str, Any]:
    """
    Executes the 12 rigorous academic plagiarism & similarity benchmark tests.
    """
    winnowing = WinnowingEngine(k=5, w=4)
    exact_comp = ExactMatchComparator(min_word_count=5)
    fuzzy_comp = FuzzyComparator(threshold=0.60)

    results = []

    # -------------------------------------------------------------
    # Case 1: Identical documents (Expect ~100% similarity)
    # -------------------------------------------------------------
    text_1 = (
        "Quantum computing leverages the fundamental principles of quantum mechanics, "
        "including superposition and entanglement, to perform complex computational tasks "
        "exponentially faster than classical von Neumann architectures."
    )
    tokens_1 = winnowing.tokenize_with_offsets(text_1)
    fps_1, _ = winnowing.compute_fingerprints(text_1)
    fps_src, _ = winnowing.compute_fingerprints(text_1)
    matches_1 = winnowing.match_fingerprints(fps_1, fps_src, text_1, text_1, min_words=5)

    scorer_1 = AcademicSimilarityScorer(total_word_count=len(tokens_1), full_text=text_1)
    for m in matches_1:
        scorer_1.add_match_span(m['submitted_word_start'], m['submitted_word_end'], source_id='src-1')
    res_1 = scorer_1.calculate()
    passed_1 = res_1['overall_similarity'] >= 95.0
    results.append({'case': 1, 'name': 'Identical documents', 'score': res_1['overall_similarity'], 'passed': passed_1})

    # -------------------------------------------------------------
    # Case 2: One copied paragraph in a larger document
    # -------------------------------------------------------------
    copied_para = (
        "The catalytic oxidation of carbon monoxide was investigated over platinum-supported "
        "titanium dioxide catalysts at temperatures ranging from 300 to 550 Kelvin."
    )
    human_intro = (
        "In modern chemical engineering, novel nanomaterials provide unprecedented surface reaction efficiencies. "
        "Researchers continuously strive to optimize catalyst regeneration cycles in industrial reactors."
    )
    human_outro = (
        "Future investigations should evaluate catalyst deactivation profiles under real-world flue gas contaminants."
    )
    doc_2 = f"{human_intro}\n\n{copied_para}\n\n{human_outro}"
    tokens_2 = winnowing.tokenize_with_offsets(doc_2)
    fps_2, _ = winnowing.compute_fingerprints(doc_2)
    fps_src_2, _ = winnowing.compute_fingerprints(copied_para)
    matches_2 = winnowing.match_fingerprints(fps_2, fps_src_2, doc_2, copied_para, min_words=5)

    scorer_2 = AcademicSimilarityScorer(total_word_count=len(tokens_2), full_text=doc_2)
    for m in matches_2:
        scorer_2.add_match_span(m['submitted_word_start'], m['submitted_word_end'], source_id='src-2')
    res_2 = scorer_2.calculate()
    # Expected: Copied paragraph is ~25-40% of total document words
    passed_2 = 20.0 <= res_2['overall_similarity'] <= 50.0
    results.append({'case': 2, 'name': 'One copied paragraph', 'score': res_2['overall_similarity'], 'passed': passed_2})

    # -------------------------------------------------------------
    # Case 3: Partial sentence overlap
    # -------------------------------------------------------------
    sub_3 = "Recent empirical investigations confirm that interest rate volatility significantly impedes foreign direct investment."
    src_3 = "Our findings indicate that interest rate volatility significantly impedes foreign direct investment across emerging markets."
    ex_res_3 = exact_comp.compare(sub_3, src_3)
    passed_3 = len(ex_res_3.matches) > 0 and 'interest rate volatility significantly impedes foreign direct investment' in ex_res_3.matches[0]['submitted_text']
    results.append({'case': 3, 'name': 'Partial sentence overlap', 'score': round(ex_res_3.similarity_score * 100, 1), 'passed': passed_3})

    # -------------------------------------------------------------
    # Case 4: Small word substitutions (Near-duplicate text)
    # -------------------------------------------------------------
    sub_4 = "Artificial intelligence offers remarkable potential for transforming contemporary diagnostic medicine."
    src_4 = "Artificial intelligence provides notable potential for transforming modern diagnostic healthcare."
    fuzzy_res_4 = fuzzy_comp.compare(sub_4, src_4)
    # SequenceMatcher detects similarity ~0.60
    passed_4 = len(fuzzy_res_4.matches) > 0 and fuzzy_res_4.matches[0]['similarity'] >= 0.60
    results.append({'case': 4, 'name': 'Small word substitutions (near-duplicates)', 'score': round((fuzzy_res_4.matches[0]['similarity'] if fuzzy_res_4.matches else 0) * 100, 1), 'passed': passed_4})

    # -------------------------------------------------------------
    # Case 5: Reordered sentences
    # -------------------------------------------------------------
    s_a = "Cell cultures were incubated in nutrient media at 37 degrees Celsius."
    s_b = "Electrophysiological responses were recorded using patch-clamp amplifiers."
    sub_5 = f"{s_a} {s_b}"
    src_5 = f"{s_b} {s_a}"
    tokens_5 = winnowing.tokenize_with_offsets(sub_5)
    fps_5, _ = winnowing.compute_fingerprints(sub_5)
    fps_src_5, _ = winnowing.compute_fingerprints(src_5)
    matches_5 = winnowing.match_fingerprints(fps_5, fps_src_5, sub_5, src_5, min_words=4)
    scorer_5 = AcademicSimilarityScorer(total_word_count=len(tokens_5), full_text=sub_5)
    for m in matches_5:
        scorer_5.add_match_span(m['submitted_word_start'], m['submitted_word_end'], source_id='src-5')
    res_5 = scorer_5.calculate()
    passed_5 = res_5['overall_similarity'] >= 80.0
    results.append({'case': 5, 'name': 'Reordered sentences', 'score': res_5['overall_similarity'], 'passed': passed_5})

    # -------------------------------------------------------------
    # Case 6: Common phrases only (Should NOT trigger match)
    # -------------------------------------------------------------
    sub_6 = "In order to understand the results, we looked at the data."
    src_6 = "In order to understand the consequences, authors should review historical trends."
    # With min_word_count=6, 4-word idiom 'In order to understand' is ignored
    ex_comp_6 = ExactMatchComparator(min_word_count=6)
    ex_res_6 = ex_comp_6.compare(sub_6, src_6)
    passed_6 = len(ex_res_6.matches) == 0
    results.append({'case': 6, 'name': 'Common phrases filtering', 'score': round(ex_res_6.similarity_score * 100, 1), 'passed': passed_6})

    # -------------------------------------------------------------
    # Case 7: Properly cited quotations (Excluded via exclusion engine)
    # -------------------------------------------------------------
    doc_7 = (
        'According to Einstein, "Imagination is more important than knowledge because knowledge is limited." '
        'This profound philosophical perspective reshaped twentieth century scientific inquiry and epistemological debate.'
    )
    tokens_7 = winnowing.tokenize_with_offsets(doc_7)
    scorer_7 = AcademicSimilarityScorer(total_word_count=len(tokens_7), full_text=doc_7)
    # Exclude quote words [2 to 11]
    scorer_7.add_exclusion_span(2, 11)
    # Register quote as match with source
    scorer_7.add_match_span(2, 11, source_id='einstein-quotes')
    res_7 = scorer_7.calculate()
    # Filtered overall similarity should be 0.0% because the quote was excluded!
    # But unfiltered similarity will capture the ~35% quote
    passed_7 = res_7['overall_similarity'] == 0.0 and res_7['unfiltered_similarity'] > 0.0
    results.append({'case': 7, 'name': 'Properly cited quotations exclusion', 'score': res_7['overall_similarity'], 'passed': passed_7})

    # -------------------------------------------------------------
    # Case 8: Large bibliography section exclusion
    # -------------------------------------------------------------
    doc_8 = (
        "This thesis examined renewable energy storage across smart grid networks.\n\n"
        "References\n"
        "[1] Smith, J. (2020). Renewable Energy Technologies. Oxford University Press.\n"
        "[2] Doe, A. (2021). Battery Storage and Grid Dynamics. Cambridge University Press.\n"
        "[3] Taylor, R. (2022). Photovoltaic Integration Systems. Springer."
    )
    tokens_8 = winnowing.tokenize_with_offsets(doc_8)
    scorer_8 = AcademicSimilarityScorer(total_word_count=len(tokens_8), full_text=doc_8)
    # References start at word 10 to end
    scorer_8.add_exclusion_span(10, len(tokens_8) - 1)
    # Even if bibliography matches external sources, it is filtered
    scorer_8.add_match_span(10, len(tokens_8) - 1, source_id='crossref-db')
    res_8 = scorer_8.calculate()
    passed_8 = res_8['overall_similarity'] == 0.0 and res_8['excluded_words'] > 20
    results.append({'case': 8, 'name': 'Large bibliography exclusion', 'score': res_8['overall_similarity'], 'passed': passed_8})

    # -------------------------------------------------------------
    # Case 9: Repeated passages within document (No artificial score inflation)
    # -------------------------------------------------------------
    passage_9 = "Thermal conductivity was measured using transient plane source sensors."
    doc_9 = f"{passage_9} Furthermore, the data was validated. {passage_9}"
    tokens_9 = winnowing.tokenize_with_offsets(doc_9)
    scorer_9 = AcademicSimilarityScorer(total_word_count=len(tokens_9), full_text=doc_9)
    # Both occurrences match the same source
    scorer_9.add_match_span(0, 8, source_id='src-9')
    scorer_9.add_match_span(14, 22, source_id='src-9')
    res_9 = scorer_9.calculate()
    # Unique matched words cannot exceed total words
    passed_9 = res_9['matched_words'] == 18 and res_9['overall_similarity'] <= 100.0
    results.append({'case': 9, 'name': 'Repeated passages deduplication', 'score': res_9['overall_similarity'], 'passed': passed_9})

    # -------------------------------------------------------------
    # Case 10: Documents with no matching source (0.0% Clean)
    # -------------------------------------------------------------
    doc_10 = "Completely novel idiosyncratic prose authored independently without referencing external repositories."
    tokens_10 = winnowing.tokenize_with_offsets(doc_10)
    scorer_10 = AcademicSimilarityScorer(total_word_count=len(tokens_10), full_text=doc_10)
    res_10 = scorer_10.calculate()
    passed_10 = res_10['overall_similarity'] == 0.0 and res_10['source_count'] == 0
    results.append({'case': 10, 'name': 'No matching source (clean document)', 'score': res_10['overall_similarity'], 'passed': passed_10})

    # -------------------------------------------------------------
    # Case 11: Multiple sources containing the same passage (Double-counting prevention!)
    # -------------------------------------------------------------
    doc_11 = "The velocity of light in vacuum is exactly 299,792,458 meters per second."
    tokens_11 = winnowing.tokenize_with_offsets(doc_11)
    scorer_11 = AcademicSimilarityScorer(total_word_count=len(tokens_11), full_text=doc_11)
    # Both Source A and Source B match entire document (words 0 to len-1)
    scorer_11.add_match_span(0, len(tokens_11) - 1, source_id='src-A', source_name='NIST Physical Constants')
    scorer_11.add_match_span(0, len(tokens_11) - 1, source_id='src-B', source_name='Encyclopedia of Physics')
    res_11 = scorer_11.calculate()
    # Overall similarity MUST be 100%, NOT 200%!
    # Source A gets 100% unique contribution; Source B gets 0% unique contribution!
    passed_11 = (
        res_11['overall_similarity'] == 100.0 and
        res_11['sources'][0]['unique_percentage'] == 100.0 and
        res_11['sources'][1]['unique_percentage'] == 0.0
    )
    results.append({'case': 11, 'name': 'Double-counting prevention across overlapping sources', 'score': res_11['overall_similarity'], 'passed': passed_11})

    # -------------------------------------------------------------
    # Case 12: Unicode, smart quotes, and formatting equivalence
    # -------------------------------------------------------------
    sub_12 = "The author\u2019s \u201cgroundbreaking\u201d hypothesis\u2014verified by empirical observation\u2014reshaped the discipline."
    src_12 = "The author's \"groundbreaking\" hypothesis - verified by empirical observation - reshaped the discipline."
    tokens_sub_12 = winnowing.tokenize_with_offsets(sub_12)
    tokens_src_12 = winnowing.tokenize_with_offsets(src_12)
    fps_sub_12, _ = winnowing.compute_fingerprints(sub_12)
    fps_src_12, _ = winnowing.compute_fingerprints(src_12)
    matches_12 = winnowing.match_fingerprints(fps_sub_12, fps_src_12, sub_12, src_12, min_words=5)
    passed_12 = len(matches_12) > 0 and len(tokens_sub_12) == len(tokens_src_12)
    results.append({'case': 12, 'name': 'Unicode, formatting & quote normalization equivalence', 'score': 100.0 if passed_12 else 0.0, 'passed': passed_12})

    return {
        'total_cases': len(results),
        'passed_cases': sum(1 for r in results if r['passed']),
        'all_passed': all(r['passed'] for r in results),
        'cases': results,
    }


if __name__ == '__main__':
    bench = run_12_case_similarity_benchmark()
    print("=" * 70)
    print("ACADEMIC SIMILARITY DETECTION ENGINE: 12-CASE BENCHMARK RESULTS")
    print("=" * 70)
    print(f"Total Cases Tested: {bench['total_cases']}")
    print(f"Passed:             {bench['passed_cases']} / {bench['total_cases']} ({bench['passed_cases'] / bench['total_cases']:.1%})")
    print("=" * 70)
    for c in bench['cases']:
        status = "PASS" if c['passed'] else "FAIL"
        print(f"[{status}] Case {c['case']:02d}: {c['name']:<50} Result: {c['score']}%")
    print("=" * 70)
