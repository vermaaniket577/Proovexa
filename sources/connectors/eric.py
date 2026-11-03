"""
Connector for ERIC (Education Resources Information Center) API.
Official U.S. Department of Education database with over 1.5 million bibliographic records and full-text papers.
"""
from datetime import datetime
import logging
from typing import List, Optional
import requests

from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class ERICConnector(BaseSourceConnector):
    """
    Connects to the official ERIC public API (api.ies.ed.gov/eric).
    Provides free open access to educational research, dissertations, and conference proceedings.
    """

    @property
    def id(self) -> str:
        return 'eric'

    @property
    def name(self) -> str:
        return 'ERIC (Education Resources Information Center)'

    @property
    def source_type(self) -> str:
        return 'open_access'

    @property
    def description(self) -> str:
        return 'U.S. Department of Education database covering peer-reviewed education research, journals, and dissertations.'

    @property
    def supports_full_text(self) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 3:
            return []

        search_query = ' '.join(query_text.split()[:10])
        url = 'https://api.ies.ed.gov/eric/'
        params = {
            'search': search_query,
            'format': 'json',
            'rows': max_results,
        }
        headers = {
            'User-Agent': 'ProovexaSimilarityEngine/2.0 (Academic research; mailto:support@proovexa.com)'
        }

        results = []
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=6.0)
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get('response', {}).get('docs', [])
                for doc in docs:
                    title = doc.get('title', '')
                    description = doc.get('description', '')
                    authors = ', '.join(doc.get('author', [])) if isinstance(doc.get('author'), list) else doc.get('author', '')
                    eric_id = doc.get('id', '')
                    doc_url = doc.get('url', f"https://eric.ed.gov/?id={eric_id}" if eric_id else "")
                    pub_year = doc.get('publicationdateyear')
                    pub_date = None
                    if pub_year:
                        try:
                            pub_date = datetime(int(pub_year), 1, 1).date()
                        except (ValueError, TypeError):
                            pass

                    # Extract available full text or comprehensive abstract
                    content_text = description or title

                    if title:
                        results.append(SourceProviderResult(
                            title=title,
                            author=authors,
                            publication_date=pub_date,
                            url=doc_url,
                            doi=doc.get('e_doi', ''),
                            text=content_text,
                            source_type='open_access',
                            provider_name='ERIC',
                            journal_or_publisher=doc.get('source', 'ERIC'),
                            access_limitations='Public Domain / Open Access'
                        ))
        except Exception as e:
            logger.debug(f"ERIC search error: {e}")

        return results
