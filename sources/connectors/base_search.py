"""
Connector for BASE (Bielefeld Academic Search Engine).
One of the world's most voluminous search engines for academic web resources, indexing 300M+ documents.
"""
from datetime import datetime
import logging
from typing import List, Optional
import requests

from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class BASEConnector(BaseSourceConnector):
    """
    Connects to the Bielefeld Academic Search Engine (BASE).
    Provides indexed metadata and open access repository documents worldwide.
    """

    @property
    def id(self) -> str:
        return 'base'

    @property
    def name(self) -> str:
        return 'BASE (Bielefeld Academic Search Engine)'

    @property
    def source_type(self) -> str:
        return 'open_access'

    @property
    def description(self) -> str:
        return 'Bielefeld University academic search engine indexing 300M+ scientific records from 10,000+ repository sources.'

    @property
    def supports_full_text(self) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 3:
            return []

        search_query = ' '.join(query_text.split()[:10])
        # OpenURL / public API query endpoint
        url = 'https://api.base-search.net/cgi-bin/sys/mbx/base_xml.pl'
        params = {
            'func': 'PerformSearch',
            'query': search_query,
            'hits': max_results,
            'format': 'json',
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
                    title = doc.get('dcf_title', [''])[0] if isinstance(doc.get('dcf_title'), list) else doc.get('dcf_title', '')
                    abstract = doc.get('dcf_description', [''])[0] if isinstance(doc.get('dcf_description'), list) else doc.get('dcf_description', '')
                    authors = ', '.join(doc.get('dcf_creator', [])) if isinstance(doc.get('dcf_creator'), list) else doc.get('dcf_creator', '')
                    doc_url = doc.get('dcf_identifier', [''])[0] if isinstance(doc.get('dcf_identifier'), list) else doc.get('dcf_identifier', '')
                    doi = doc.get('dcf_doi', '')

                    if title:
                        results.append(SourceProviderResult(
                            title=title,
                            author=authors,
                            url=doc_url or f"https://www.base-search.net/Search/Results?q={search_query}",
                            doi=doi,
                            text=abstract or title,
                            source_type='open_access',
                            provider_name='BASE',
                            journal_or_publisher='BASE Bielefeld',
                            access_limitations='Open Access Repository'
                        ))
        except Exception as e:
            logger.debug(f"BASE search error: {e}")

        return results
