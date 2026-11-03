"""
CORE REST API Connector.
https://core.ac.uk/ - World's largest collection of open access research papers.
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
        return getattr(settings, 'CORE_API_KEY', os.environ.get('CORE_API_KEY', ''))
    except Exception:
        return os.environ.get('CORE_API_KEY', '')


class COREConnector(BaseSourceConnector):
    """Connector for CORE open-access research API."""

    @property
    def id(self) -> str:
        return 'core'

    @property
    def name(self) -> str:
        return 'CORE'

    @property
    def source_type(self) -> str:
        return 'open_access'

    @property
    def description(self) -> str:
        return (
            "Aggregates 250+ million open access research papers from thousands of institutional "
            "and subject repositories globally."
        )

    @property
    def requires_api_key(self) -> bool:
        return True

    @property
    def api_key_name(self) -> str:
        return 'CORE_API_KEY'

    def is_available(self) -> bool:
        return bool(_get_api_key())

    def _get_headers(self):
        api_key = _get_api_key()
        headers = {'User-Agent': 'ProovexaSimilarityEngine/2.0'}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        return headers

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not self.is_available():
            logger.info("CORE API Key not configured; skipping CORE search")
            return []

        if not query_text or len(query_text.strip()) < 4:
            return []

        url = "https://api.core.ac.uk/v3/search/works"
        params = {
            'q': query_text.strip()[:180],
            'limit': min(max_results, 6),
        }

        try:
            resp = requests.get(url, params=params, headers=self._get_headers(), timeout=7)
            if resp.status_code != 200:
                logger.warning(f"CORE API returned HTTP {resp.status_code}")
                return []

            data = resp.json()
            items = data.get('results', [])
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

                doi = item.get('doi', '')
                download_url = item.get('downloadUrl', '') or (f"https://doi.org/{doi}" if doi else "")

                pub_date = None
                pub_year = item.get('yearPublished')
                if pub_year:
                    try:
                        pub_date = datetime(int(pub_year), 1, 1).date()
                    except Exception:
                        pass

                content_text = f"{title}. {abstract}" if abstract else title

                results.append(SourceProviderResult(
                    title=title,
                    author=author_str,
                    publication_date=pub_date,
                    url=download_url,
                    doi=doi,
                    text=content_text,
                    source_type='open_access',
                    provider_name='CORE',
                    access_limitations='CORE Open Access Aggregator API',
                    raw_metadata=item,
                ))

            return results
        except Exception as e:
            logger.warning(f"CORE search exception: {e}")
            return []

    def get_rate_limit_info(self) -> dict:
        api_key = getattr(settings, 'CORE_API_KEY', os.environ.get('CORE_API_KEY', ''))
        return {
            'rate_limit': 'Depends on CORE API plan (Free tier: 10 requests/minute)',
            'terms_url': 'https://core.ac.uk/services/api',
            'license_info': 'CORE API Data Provider Agreement',
            'has_key': bool(api_key),
        }
