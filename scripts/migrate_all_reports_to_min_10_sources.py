import os
import sys
import django

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagiarism_project.settings')
django.setup()

from analysis.models import SimilarityReport
from reports.criteria import compute_report_criteria

def migrate():
    reports = SimilarityReport.objects.filter(overall_similarity__gt=0).order_by('-created_at')
    print(f"[+] Total reports with >0% similarity: {reports.count()}", flush=True)

    updated_count = 0
    for r in reports:
        cnt_before = len(r.source_breakdown or [])
        if cnt_before < 10:
            try:
                crit = compute_report_criteria(r)
                r.refresh_from_db()
                cnt_after = len(r.source_breakdown or [])
                updated_count += 1
                doc_title = (r.document.title or r.document.original_filename) if r.document else 'No Doc'
                print(f"[+] Report {r.id} ({doc_title}): {cnt_before} -> {cnt_after} sources", flush=True)
            except Exception as e:
                print(f"[!] Error on Report {r.id}: {e}", flush=True)

    print(f"[+] Migration complete! Updated {updated_count} reports to have minimum 10 sources.", flush=True)

if __name__ == '__main__':
    migrate()

