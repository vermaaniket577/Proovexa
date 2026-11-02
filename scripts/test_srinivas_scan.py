import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagiarism_project.settings')
import django; django.setup()

from documents.models import Document
from analysis.engine import AnalysisEngine
from reports.criteria import compute_report_criteria

doc = Document.objects.get(id='8f2362c7-7070-4a5f-a25b-c86bde4ec7dc')
print(f"Scanning document: '{doc.title}' ({doc.id})")
print(f"Word count: {doc.word_count}")

engine = AnalysisEngine(exclusion_settings={
    'exclude_bibliography': True,
    'exclude_quotes': True,
    'exclude_self_match': True,
    'min_match_words': 8,
    'check_web_sources': False,
})

t0 = time.time()
report = engine.analyze_document(doc, user=doc.uploaded_by)
duration = time.time() - t0

print(f"\nAnalysis completed in {duration:.2f} seconds!")
print(f"Overall similarity: {report.overall_similarity}%")
print(f"Total matched chunks: {report.matched_passages.count()}")
print(f"Total sources found: {report.source_count}")

criteria = compute_report_criteria(report)
print("Submission ID:", criteria['submission_id'])
print("Score Display:", criteria['score_display'])
print("Database Breakdown:")
for d in criteria['database_sources']:
    print(f"  {d['name']}: {d['percent']}")

print("Match Groups:")
for g in criteria['match_groups']:
    print(f"  {g['name']}: {g['count']} ({g['percent']})")

print(f"\nTop Sources ({len(criteria['top_sources'])} total):")
for s in criteria['top_sources'][:15]:
    print(f"  [{s['index']}] {s['category']}: {s['title'][:55]} ({s['percent']})")
