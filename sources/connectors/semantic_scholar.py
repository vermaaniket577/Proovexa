"""
Semantic Scholar REST API Connector.
https://www.semanticscholar.org/ - AI-backed scientific literature search by Allen Institute for AI.
"""
import os
import logging
import requests
from typing import List
from datetime import datetime
from django.conf import settings
from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


def _get_api_key():
    try:
        from django.conf import settings
        return getattr(settings, 'SEMANTIC_SCHOLAR_API_KEY', os.environ.get('SEMANTIC_SCHOLAR_API_KEY', ''))
    except Exception:
        return os.environ.get('SEMANTIC_SCHOLAR_API_KEY', '')


class SemanticScholarConnector(BaseSourceConnector):
    """Connector for Semantic Scholar Graph API."""

    @property
    def id(self) -> str:
        return 'semantic_scholar'

    @property
    def name(self) -> str:
        return 'Semantic Scholar'

    @property
    def source_type(self) -> str:
        return 'academic'

    @property
    def description(self) -> str:
        return (
            "Allen Institute for AI scholarly search engine covering 200+ million scientific papers "
            "with contextual citation graphs, AI abstracts, and open-access links."
        )

    @property
    def requires_api_key(self) -> bool:
        return False  # Works with or without API key (key provides higher rate limits)

    @property
    def api_key_name(self) -> str:
        return 'SEMANTIC_SCHOLAR_API_KEY'

    def is_available(self) -> bool:
        return True

    def _get_headers(self):
        headers = {'User-Agent': 'ProovexaSimilarityEngine/2.0'}
        api_key = _get_api_key()
        if api_key:
            headers['x-api-key'] = api_key
        return headers

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 4:
            return []

        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            'query': query_text.strip()[:180],
            'limit': min(max_results, 6),
            'fields': 'title,abstract,authors,year,url,externalIds,venue,openAccessPdf',
        }

        try:
            resp = requests.get(url, params=params, headers=self._get_headers(), timeout=6)
            if resp.status_code == 429:
                logger.info("Semantic Scholar API 429 (Rate limit reached without key; skipping)")
                return []
            if resp.status_code != 200:
                logger.warning(f"Semantic Scholar returned HTTP {resp.status_code}")
                return []

            data = resp.json()
            items = data.get('data', [])
            results = []

            for item in items:
                title = item.get('title', '').strip()
                if not title:
                    continue

                abstract = item.get('abstract', '') or ''
                authors = [a.get('name', '') for a in item.get('authors', []) if a.get('name')]
                author_str = ", ".join(authors[:3])
                if len(authors) > 3:
                    author_str += " et al."

                ext_ids = item.get('externalIds', {}) or {}
                doi = ext_ids.get('DOI', '')

                # Link: openAccessPdf URL or external URL
                oa_pdf = item.get('openAccessPdf', {}) or {}
                item_url = oa_pdf.get('url', '') or item.get('url', '') or (f"https://doi.org/{doi}" if doi else "")

                pub_date = None
                year = item.get('year')
                if year:
                    try:
                        pub_date = datetime(int(year), 1, 1).date()
                    except Exception:
                        pass

                venue = item.get('venue', '')
                content_text = f"{title}. {abstract}" if abstract else title

                results.append(SourceProviderResult(
                    title=title,
                    author=author_str,
                    publication_date=pub_date,
                    url=item_url,
                    doi=doi,
                    text=content_text,
                    source_type='academic',
                    provider_name='Semantic Scholar',
                    journal_or_publisher=venue,
                    access_limitations='Semantic Scholar API Terms of Use',
                    raw_metadata=item,
                ))

            return results
        except Exception as e:
            logger.warning(f"Semantic Scholar search exception: {e}")
            return []

    def get_rate_limit_info(self) -> dict:
        api_key = getattr(settings, 'SEMANTIC_SCHOLAR_API_KEY', os.environ.get('SEMANTIC_SCHOLAR_API_KEY', ''))
        return {
            'rate_limit': '100 requests/5 minutes (Unauthenticated) or 100 req/sec (with SEMANTIC_SCHOLAR_API_KEY)',
            'terms_url': 'https://www.semanticscholar.org/product/api',
            'license_info': 'Semantic Scholar Academic Graph License',
            'has_key': bool(api_key),
        }
