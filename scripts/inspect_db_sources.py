import os, sys
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagiarism_project.settings')
import django
django.setup()

from documents.models import ReferenceSource

sources = list(ReferenceSource.objects.all().order_by('id'))
print(f'Total ReferenceSources in DB: {len(sources)}')

tags = {}
for s in sources:
    tag = s.access_limitations or 'No tag'
    tags[tag] = tags.get(tag, 0) + 1

for tag, count in tags.items():
    print(f'Tag: "{tag}" -> {count} sources')
