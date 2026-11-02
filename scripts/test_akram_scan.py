import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagiarism_project.settings')
import django; django.setup()

from documents.models import Document
from analysis.engine import AnalysisEngine
from reports.criteria import compute_report_criteria

doc = Document.objects.get(id='fb082767-33fa-4e4e-8546-6bee5a2e7ad9')
print(f"Scanning document: '{doc.title}' ({doc.id})")

engine = AnalysisEngine(exclusion_settings={
    'exclude_bibliography': True,
    'exclude_quotes': True,
    'min_match_words': 8,
    'check_web_sources': False,
})

t0 = time.time()
report = engine.analyze_document(doc)
duration = time.time() - t0

print(f"\nAnalysis completed in {duration:.2f} seconds!")
print(f"Overall similarity: {report.overall_similarity}%")
print(f"Total matched chunks: {report.matched_passages.count()}")

criteria = compute_report_criteria(report)

print("Submission ID:", criteria['submission_id'])
print("Score Display:", criteria['score_display'])
print("Database Breakdown:")
for d in criteria['database_sources']:
    print(f"  {d['name']}: {d['percent']}")

print("Match Groups:")
for g in criteria['match_groups']:
    print(f"  {g['name']}: {g['count']} ({g['percent']})")

print(f"Top Sources ({len(criteria['top_sources'])} total):")
for s in criteria['top_sources']:
    print(f"  [{s['index']}] {s['category']}: {s['title'][:55]} ({s['percent']})")
