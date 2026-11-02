import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagiarism_project.settings')
import django; django.setup()

from documents.models import Document
from reports.criteria import compute_report_criteria

doc = Document.objects.filter(title__icontains='Sarhad').first()
report = doc.latest_similarity_report
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
for s in criteria['top_sources']:
    print(f"  [{s['index']}] {s['category']}: {s['title'][:60]} ({s['percent']})")
