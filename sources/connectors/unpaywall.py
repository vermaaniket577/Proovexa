"""
Unpaywall REST API Connector.
https://unpaywall.org/ - Legal open-access versions of research articles.
"""
import os
import logging
import requests
from typing import List, Optional
from django.conf import settings
from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class UnpaywallConnector(BaseSourceConnector):
    """Connector for Unpaywall DOI open-access locator API."""

    @property
    def id(self) -> str:
        return 'unpaywall'

    @property
    def name(self) -> str:
        return 'Unpaywall'

    @property
    def source_type(self) -> str:
        return 'open_access'

    @property
    def description(self) -> str:
        return (
            "Database of 50+ million free, legally accessible scholarly articles harvested from "
            "over 50,000 journals and institutional repositories worldwide."
        )

    def is_available(self) -> bool:
        return True

    def _get_email(self) -> str:
        try:
            from django.conf import settings
            return getattr(settings, 'UNPAYWALL_EMAIL', os.environ.get('UNPAYWALL_EMAIL', 'admin@proovexa.edu'))
        except Exception:
            return os.environ.get('UNPAYWALL_EMAIL', 'admin@proovexa.edu')

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        # Unpaywall is primarily DOI-indexed. If query_text is a DOI, we resolve directly.
        # Otherwise, title-based discovery is handled via Crossref/OpenAlex and enriched by Unpaywall.
        import re
        doi_match = re.search(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+', query_text)
        if not doi_match:
            return []

        doi = doi_match.group(0)
        res = self.lookup_doi(doi)
        return [res] if res else []

    def lookup_doi(self, doi: str) -> Optional[SourceProviderResult]:
        """Looks up a specific DOI on Unpaywall to find open-access versions."""
        if not doi:
            return None

        clean_doi = doi.strip().replace('https://doi.org/', '').replace('http://doi.org/', '')
        email = self._get_email()
        url = f"https://api.unpaywall.org/v2/{clean_doi}?email={email}"

        try:
            resp = requests.get(url, headers={'User-Agent': 'ProovexaUnpaywall/2.0'}, timeout=6)
            if resp.status_code != 200:
                return None

            data = resp.json()
            title = data.get('title', '')
            oa_locations = data.get('oa_locations', [])
            best_oa = data.get('best_oa_location') or (oa_locations[0] if oa_locations else {})
            oa_url = best_oa.get('url_for_pdf') or best_oa.get('url_for_landing_page') or data.get('doi_url', '')

            author_str = ", ".join(a.get('family', '') for a in data.get('z_authors', [])[:3] if a.get('family'))

            return SourceProviderResult(
                title=title,
                author=author_str,
                url=oa_url,
                doi=clean_doi,
                text=title,
                source_type='open_access',
                provider_name='Unpaywall',
                journal_or_publisher=data.get('journal_name', ''),
                access_limitations='Unpaywall Open Access Registry',
                raw_metadata=data,
            )
        except Exception as e:
            logger.debug(f"Unpaywall DOI lookup error for {doi}: {e}")
            return None

    def get_rate_limit_info(self) -> dict:
        return {
            'rate_limit': '100,000 calls per day with valid email parameter',
            'terms_url': 'https://unpaywall.org/user-agreement',
            'license_info': 'OurResearch Open Data / Open Access Policy',
        }
