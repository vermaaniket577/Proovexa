"""
OpenAlex REST API Connector.
https://openalex.org/ - Scholarly works, authors, institutions, reconstructed full abstracts, and open-access links.
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
        return getattr(settings, 'OPENALEX_MAILTO', os.environ.get('OPENALEX_MAILTO', 'admin@proovexa.edu'))
    except Exception:
        return os.environ.get('OPENALEX_MAILTO', 'admin@proovexa.edu')


def reconstruct_openalex_abstract(inverted_index: dict) -> str:
    """Reconstructs linear text from OpenAlex abstract_inverted_index."""
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    word_positions = []
    for word, positions in inverted_index.items():
        if isinstance(positions, list):
            for pos in positions:
                word_positions.append((pos, word))
    word_positions.sort(key=lambda x: x[0])
    return " ".join(w for _, w in word_positions)


class OpenAlexConnector(BaseSourceConnector):
    """Connector for OpenAlex global scholarly graph API."""

    @property
    def id(self) -> str:
        return 'openalex'

    @property
    def name(self) -> str:
        return 'OpenAlex'

    @property
    def source_type(self) -> str:
        return 'open_access'

    @property
    def description(self) -> str:
        return (
            "Open index of over 250 million scholarly publications, reconstructed full abstracts, "
            "author affiliations, citation graphs, and direct open-access PDF links."
        )

    def is_available(self) -> bool:
        # OpenAlex API is completely free and public
        return True

    def _get_headers(self):
        mailto = _get_mailto()
        return {
            'User-Agent': f'ProovexaAcademicIntegrity/2.0 (mailto:{mailto})',
            'Accept': 'application/json',
        }

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 4:
            return []

        url = "https://api.openalex.org/works"
        params = {
            'search': query_text.strip()[:200],
            'per-page': min(max_results, 10),
            'mailto': _get_mailto(),
        }

        try:
            resp = requests.get(url, params=params, headers=self._get_headers(), timeout=7)
            if resp.status_code != 200:
                logger.warning(f"OpenAlex API returned HTTP {resp.status_code}")
                return []

            data = resp.json()
            results_raw = data.get('results', [])
            results = []

            for item in results_raw:
                title = item.get('title') or item.get('display_name') or 'Untitled Scholarly Work'

                # Authors
                authors_list = []
                for auth in item.get('authorships', []):
                    name = auth.get('author', {}).get('display_name', '')
                    if name:
                        authors_list.append(name)
                author_str = ", ".join(authors_list[:3])
                if len(authors_list) > 3:
                    author_str += " et al."

                # Publication date
                pub_date = None
                pub_date_str = item.get('publication_date')
                if pub_date_str:
                    try:
                        pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d').date()
                    except Exception:
                        pass

                doi = item.get('doi', '')
                if doi and doi.startswith('https://doi.org/'):
                    doi = doi[len('https://doi.org/'):]

                # Link: prefer open-access PDF URL, then primary landing page, then DOI
                oa_info = item.get('open_access', {}) or {}
                oa_url = oa_info.get('oa_url', '')
                primary_loc = item.get('primary_location', {}) or {}
                landing_url = primary_loc.get('landing_page_url', '') or item.get('id', '')
                final_url = oa_url or landing_url or (f"https://doi.org/{doi}" if doi else "")

                # Abstract
                inverted_idx = item.get('abstract_inverted_index')
                abstract = reconstruct_openalex_abstract(inverted_idx)

                # Source/Journal venue
                venue = primary_loc.get('source', {}).get('display_name', '') if primary_loc.get('source') else ''

                content_text = f"{title}. {abstract}" if abstract else title

                results.append(SourceProviderResult(
                    title=title,
                    author=author_str,
                    publication_date=pub_date,
                    url=final_url,
                    doi=doi,
                    text=content_text,
                    source_type='open_access' if oa_info.get('is_oa') else 'academic',
                    provider_name='OpenAlex',
                    journal_or_publisher=venue,
                    access_limitations='OpenAlex CC0 Scholarly Graph API',
                    raw_metadata=item,
                ))

            return results
        except Exception as e:
            logger.warning(f"OpenAlex search exception: {e}")
            return []

    def get_rate_limit_info(self) -> dict:
        return {
            'rate_limit': '100,000 requests/day, 10 requests/sec with polite email',
            'terms_url': 'https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication',
            'license_info': 'Creative Commons CC0 Public Domain Attribution',
        }
