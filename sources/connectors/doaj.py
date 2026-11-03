"""
DOAJ (Directory of Open Access Journals) API Connector.
https://doaj.org/ - High-quality, peer-reviewed open access research journals.
"""
import logging
import requests
from typing import List
from datetime import datetime
from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class DOAJConnector(BaseSourceConnector):
    """Connector for Directory of Open Access Journals (DOAJ) articles API."""

    @property
    def id(self) -> str:
        return 'doaj'

    @property
    def name(self) -> str:
        return 'DOAJ'

    @property
    def source_type(self) -> str:
        return 'open_access'

    @property
    def description(self) -> str:
        return (
            "Independent global directory indexing over 20,000 peer-reviewed open access journals "
            "and 10+ million full-text research articles across all disciplines."
        )

    def is_available(self) -> bool:
        return True

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 4:
            return []

        import urllib.parse
        clean_q = query_text.strip().replace('/', ' ')[:150]
        url = f"https://doaj.org/api/v2/search/articles/{urllib.parse.quote(clean_q)}"
        params = {
            'pageSize': min(max_results, 6),
        }

        try:
            resp = requests.get(url, params=params, headers={'User-Agent': 'ProovexaDOAJConnector/2.0'}, timeout=7)
            if resp.status_code != 200:
                logger.warning(f"DOAJ API returned HTTP {resp.status_code}")
                return []

            data = resp.json()
            items = data.get('results', [])
            results = []

            for item in items:
                bib = item.get('bibjson', {})
                title = bib.get('title', '').strip()
                if not title:
                    continue

                abstract = bib.get('abstract', '') or ''

                # Authors
                authors = [a.get('name', '') for a in bib.get('author', []) if a.get('name')]
                author_str = ", ".join(authors[:3])
                if len(authors) > 3:
                    author_str += " et al."

                # DOI
                doi = ""
                for ident in bib.get('identifier', []):
                    if ident.get('type') == 'doi':
                        doi = ident.get('id', '')

                # Links
                links = bib.get('link', [])
                item_url = ""
                for lk in links:
                    if lk.get('type') == 'fulltext':
                        item_url = lk.get('url', '')
                        break
                if not item_url and doi:
                    item_url = f"https://doi.org/{doi}"

                # Date
                pub_date = None
                year = bib.get('year')
                if year:
                    try:
                        pub_date = datetime(int(year), 1, 1).date()
                    except Exception:
                        pass

                journal = bib.get('journal', {}).get('title', '')
                content_text = f"{title}. {abstract}" if abstract else title

                results.append(SourceProviderResult(
                    title=title,
                    author=author_str,
                    publication_date=pub_date,
                    url=item_url,
                    doi=doi,
                    text=content_text,
                    source_type='open_access',
                    provider_name='DOAJ',
                    journal_or_publisher=journal,
                    access_limitations='DOAJ Open Access Directory',
                    raw_metadata=item,
                ))

            return results
        except Exception as e:
            logger.warning(f"DOAJ search exception: {e}")
            return []

    def get_rate_limit_info(self) -> dict:
        return {
            'rate_limit': 'Open API, recommended max 5 requests/sec',
            'terms_url': 'https://doaj.org/api/v2/docs',
            'license_info': 'DOAJ Creative Commons BY-SA Attribution',
        }
