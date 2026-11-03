"""
Crossref REST API Connector.
https://www.crossref.org/ - Scholarly research article metadata, titles, DOIs, authors, publication dates.
"""
import os
import logging
import requests
from typing import List
from datetime import datetime
from django.conf import settings
from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


def _get_mailto():
    try:
        from django.conf import settings
        return getattr(settings, 'CROSSREF_MAILTO', os.environ.get('CROSSREF_MAILTO', 'admin@proovexa.edu'))
    except Exception:
        return os.environ.get('CROSSREF_MAILTO', 'admin@proovexa.edu')


class CrossrefConnector(BaseSourceConnector):
    """Connector for Crossref public metadata API."""

    @property
    def id(self) -> str:
        return 'crossref'

    @property
    def name(self) -> str:
        return 'Crossref'

    @property
    def source_type(self) -> str:
        return 'academic'

    @property
    def description(self) -> str:
        return (
            "API gateway to over 150 million open research metadata records, DOIs, "
            "journal articles, conference proceedings, and publisher citations."
        )

    def is_available(self) -> bool:
        # Crossref public API is open and freely accessible without an API key
        return True

    def _get_headers(self):
        mailto = _get_mailto()
        return {
            'User-Agent': f'ProovexaAcademicChecker/2.0 (mailto:{mailto})',
            'Accept': 'application/json',
        }

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 4:
            return []

        url = "https://api.crossref.org/works"
        params = {
            'query': query_text.strip()[:200],
            'rows': min(max_results, 10),
            'select': 'DOI,title,author,published,URL,container-title,abstract,publisher',
        }

        try:
            resp = requests.get(url, params=params, headers=self._get_headers(), timeout=7)
            if resp.status_code != 200:
                logger.warning(f"Crossref API returned HTTP {resp.status_code}")
                return []

            data = resp.json()
            items = data.get('message', {}).get('items', [])
            results = []

            for item in items:
                raw_titles = item.get('title', [])
                title = raw_titles[0] if raw_titles else 'Untitled Crossref Record'

                # Extract authors
                authors_list = []
                for a in item.get('author', []):
                    given = a.get('given', '')
                    family = a.get('family', '')
                    name = f"{given} {family}".strip()
                    if name:
                        authors_list.append(name)
                author_str = ", ".join(authors_list[:3])
                if len(authors_list) > 3:
                    author_str += " et al."

                # Publication date
                pub_date = None
                date_parts = item.get('published', {}).get('date-parts', [])
                if date_parts and date_parts[0]:
                    parts = date_parts[0]
                    year = parts[0] if len(parts) > 0 else 2020
                    month = parts[1] if len(parts) > 1 else 1
                    day = parts[2] if len(parts) > 2 else 1
                    try:
                        pub_date = datetime(year, month, day).date()
                    except Exception:
                        pass

                doi = item.get('DOI', '')
                item_url = item.get('URL', f"https://doi.org/{doi}" if doi else "")
                abstract = item.get('abstract', '') or ''
                # Clean JATS XML tags from Crossref abstract if present
                import re
                abstract = re.sub(r'<[^>]+>', '', abstract).strip()

                journal = ""
                containers = item.get('container-title', [])
                if containers:
                    journal = containers[0]
                elif item.get('publisher'):
                    journal = item.get('publisher')

                content_text = f"{title}. {abstract}" if abstract else title

                results.append(SourceProviderResult(
                    title=title,
                    author=author_str,
                    publication_date=pub_date,
                    url=item_url,
                    doi=doi,
                    text=content_text,
                    source_type='academic',
                    provider_name='Crossref',
                    journal_or_publisher=journal,
                    access_limitations='Open Metadata API (Crossref Polite Pool)',
                    raw_metadata=item,
                ))

            return results
        except Exception as e:
            logger.warning(f"Crossref search exception: {e}")
            return []

    def get_rate_limit_info(self) -> dict:
        return {
            'rate_limit': '50 requests/sec with polite User-Agent',
            'terms_url': 'https://www.crossref.org/documentation/retrieve-metadata/rest-api/',
            'license_info': 'Creative Commons CC0 Public Domain Metadata',
        }
