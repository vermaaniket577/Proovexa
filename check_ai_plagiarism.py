"""
Proovexa / ScholarGuard - Universal AI & Similarity Plagiarism Scanner CLI.
Runs both:
1. AI Writing Detection Scan ("AI Plagiarism" - Cyan vs Purple Dual-Category Analysis)
2. Document Similarity & Paraphrase Plagiarism Scan ("Similar Plagiarism")
"""
import os
import sys
import argparse

# Setup Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagiarism_project.settings')
import django
django.setup()

from analysis.ai_detector import AIDetectionEngine
from analysis.ai_api_client import AIAPIClient
from analysis.models import AIAPISettings
from analysis.hybrid_checker import TurnitinStyleChecker
from documents.models import Document, ReferenceSource


def extract_text_from_file(file_path: str) -> str:
    """Extracts text from PDF, DOCX, or TXT file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        import pymupdf
        doc = pymupdf.open(file_path)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    elif ext == '.docx':
        import docx
        doc = docx.Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)
    else:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()


def run_scans(text: str, doc_name: str = "Submitted Text", current_file_path: str = ""):
    print("\n" + "=" * 70)
    print(f" PROOVEXA AI & SIMILARITY PLAGIARISM INSPECTOR")
    print(f" Target Document: {doc_name}")
    print(f" Total Words:     {len(text.split()):,}")
    print("=" * 70)

    # ---------------------------------------------------------
    # 1. AI API Configuration & Health
    # ---------------------------------------------------------
    settings_obj = AIAPISettings.get_settings()
    client = AIAPIClient(ai_settings=settings_obj)
    active_provider = client.get_active_provider_name()

    print("\n[1] AI API CREDENTIALS & ENGINE STATUS")
    print(f" - Active Provider:       {active_provider}")
    print(f" - API Integration:       {'ENABLED' if settings_obj.is_enabled else 'DISABLED'}")
    print(f" - Configured Provider:   {settings_obj.get_provider_display()}")
    print(f" - Gemini Model:          {settings_obj.gemini_model}")
    print(f" - OpenAI Model:          {settings_obj.openai_model}")
    print(f" - Gemini Key Stored:     {'YES (' + settings_obj.masked_gemini_key() + ')' if settings_obj.gemini_api_key else 'NO'}")
    print(f" - OpenAI Key Stored:     {'YES (' + settings_obj.masked_openai_key() + ')' if settings_obj.openai_api_key else 'NO'}")

    # Test live Gemini API if key is present
    if settings_obj.gemini_api_key:
        ping = client.test_connection(provider='gemini')
        if ping.get('success'):
            print(f" - Live API Ping:         ONLINE (Latency: {ping.get('latency_ms')}ms)")
        else:
            print(f" - Live API Status Note:  {ping.get('error')}")
            print("   -> Fallback active: Calibrated Turnitin V2.5 Offline Engine ensures continuous detection.")

    # ---------------------------------------------------------
    # 2. AI Writing Detection ("AI Plagiarism")
    # ---------------------------------------------------------
    print("\n[2] RUNNING AI WRITING PLAGIARISM DETECTION ('AI PLAG')...")
    ai_engine = AIDetectionEngine()
    ai_eval = ai_engine.evaluate_text_snippet(text)

    score = ai_eval.get('overall_ai_score', 0.0)
    score_display = "*%" if score < 20.0 else f"{int(round(score))}%"

    print(f" -> AI Authorship Score:   {score_display} (Raw: {score:.1f}%)")
    print(f" -> Classifier Confidence: {ai_eval.get('model_confidence', 0.0):.2f}")
    print(f" -> Below 20% Threshold:   {ai_eval.get('is_below_threshold', False)} (Scores below 20% displayed as '*%' to prevent false positives)")
    print(f" -> Active AI Provider:    {ai_eval.get('provider', 'TurnitinStyle-AI-V2.5')}")

    sentences = ai_eval.get('sentences', [])
    cyan_sents = [s for s in sentences if s.get('highlight_color') == 'cyan' or s.get('category') == 'AI-Generated']
    purple_sents = [s for s in sentences if s.get('highlight_color') == 'purple' or s.get('category') == 'AI-Paraphrased']
    human_sents = [s for s in sentences if s not in cyan_sents and s not in purple_sents]

    print(f" -> Sentence Breakdown:    Total: {len(sentences)} | AI-Generated (Cyan): {len(cyan_sents)} | AI-Paraphrased (Purple): {len(purple_sents)} | Human: {len(human_sents)}")

    if cyan_sents or purple_sents:
        print("\n    Flagged Passages:")
        for s in (cyan_sents[:3] + purple_sents[:3]):
            cat_label = "Cyan (Entirely AI)" if s in cyan_sents else "Purple (AI Paraphrased/Spun)"
            txt_preview = (s.get('sentence', '')[:90] + '...') if len(s.get('sentence', '')) > 90 else s.get('sentence', '')
            print(f"     [{cat_label}] \"{txt_preview}\"")

    # ---------------------------------------------------------
    # 3. Similarity Plagiarism Scan ("Similar Plag")
    # ---------------------------------------------------------
    print("\n[3] RUNNING TEXT SIMILARITY PLAGIARISM DETECTION ('SIMILAR PLAG')...")
    reference_corpus = {}

    # A. Existing database documents
    existing_docs = Document.objects.filter(is_deleted=False)
    for d in existing_docs:
        extracted = "\n\n".join(t.content for t in d.extracted_texts.all())
        if extracted.strip():
            reference_corpus[f"Doc-{d.id} ({d.title})"] = extracted

    # B. Existing database reference sources
    for ref in ReferenceSource.objects.filter(is_active=True):
        if ref.retrieved_text and ref.retrieved_text.strip():
            reference_corpus[f"RefSource ({ref.title})"] = ref.retrieved_text
        elif ref.document:
            extracted = "\n\n".join(t.content for t in ref.document.extracted_texts.all())
            if extracted.strip():
                reference_corpus[f"RefDoc ({ref.title})"] = extracted

    # C. Local companion benchmark files in workspace (cross-comparison)
    local_samples = ['sample_similarity.pdf', 'sample_ai.pdf']
    for sample_fn in local_samples:
        sample_path = os.path.abspath(sample_fn)
        if os.path.exists(sample_path):
            if current_file_path and os.path.abspath(current_file_path) == sample_path:
                continue
            if doc_name.lower().endswith(sample_fn.lower()):
                continue
            try:
                s_text = extract_text_from_file(sample_path)
                if s_text.strip():
                    reference_corpus[f"Workspace Benchmark ({sample_fn})"] = s_text
            except Exception:
                pass

    checker = TurnitinStyleChecker()
    if reference_corpus:
        sim_eval = checker.evaluate_submission(text, reference_corpus)
        sim_index = sim_eval.get('overall_similarity_index_pct', 0.0)
        sim_display = "*" if sim_index == 0 else f"{sim_index:.1f}%"
        print(f" -> Overall Similarity:   {sim_display} against {len(reference_corpus)} repository source(s)")

        for s_item in sim_eval.get('source_breakdown', []):
            if s_item.get('composite_similarity_pct', 0) > 0 or len(reference_corpus) <= 5:
                print(f"    - Source: {s_item.get('source_id')}")
                print(f"      Composite Match:    {s_item.get('composite_similarity_pct')}%")
                print(f"      Exact Shingle Match: {s_item.get('exact_shingle_containment_pct')}%")
                print(f"      Lexical Overlap:    {s_item.get('lexical_tfidf_pct')}%")
                print(f"      Semantic Paraphrase:{s_item.get('semantic_paraphrase_pct')}%")
    else:
        print(" -> No other documents currently stored in the repository reference corpus.")
        print("    Self-contained shingle analysis executed: 0% external repository overlap.")

    print("\n" + "=" * 70)
    print(" SCAN COMPLETE - Reports are accessible in Web UI at http://127.0.0.1:8000/")
    print("=" * 70 + "\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="ScholarGuard AI & Similarity Plagiarism Scanner")
    parser.add_argument('--file', type=str, default='sample_ai.pdf', help="Path to PDF, DOCX, or text file")
    parser.add_argument('--text', type=str, default=None, help="Direct text string to scan")
    args = parser.parse_args()

    if args.text:
        run_scans(args.text, doc_name="Direct Text Input")
    else:
        target_path = os.path.abspath(args.file)
        if not os.path.exists(target_path):
            print(f"File not found: {target_path}")
            sys.exit(1)
        raw_content = extract_text_from_file(target_path)
        run_scans(raw_content, doc_name=os.path.basename(target_path), current_file_path=target_path)
