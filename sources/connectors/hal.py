"""
Connector for HAL Open Science (France / CNRS / Inria).
Major European multi-disciplinary open archive containing millions of scientific documents, theses, and articles.
"""
from datetime import datetime
import logging
from typing import List, Optional
import requests

from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class HALOpenScienceConnector(BaseSourceConnector):
    """
    Connects to the official HAL Open Science REST API (api.archives-ouvertes.fr/search/).
    Covers European institutional repositories, theses, conference papers, and journal articles.
    """

    @property
    def id(self) -> str:
        return 'hal'

    @property
    def name(self) -> str:
        return 'HAL Open Science (CNRS / Inria)'

    @property
    def source_type(self) -> str:
        return 'open_access'

    @property
    def description(self) -> str:
        return 'National French and European multi-disciplinary open archive for published papers, theses, and preprints.'

    @property
    def supports_full_text(self) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 3:
            return []

        search_query = ' '.join(query_text.split()[:10])
        url = 'https://api.archives-ouvertes.fr/search/'
        params = {
            'q': search_query,
            'wt': 'json',
            'fl': 'title_s,abstract_s,uri_s,doiId_s,authFullName_s,producedDateY_i,docType_s',
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
                    titles = doc.get('title_s', [])
                    title = titles[0] if isinstance(titles, list) and titles else (titles or '')
                    abstracts = doc.get('abstract_s', [])
                    abstract = abstracts[0] if isinstance(abstracts, list) and abstracts else (abstracts or '')
                    authors = doc.get('authFullName_s', [])
                    author_str = ', '.join(authors) if isinstance(authors, list) else (authors or '')
                    uri = doc.get('uri_s', '')
                    doi = doc.get('doiId_s', '')
                    year = doc.get('producedDateY_i')
                    pub_date = None
                    if year:
                        try:
                            pub_date = datetime(int(year), 1, 1).date()
                        except (ValueError, TypeError):
                            pass

                    content_text = abstract or title

                    if title:
                        results.append(SourceProviderResult(
                            title=title,
                            author=author_str,
                            publication_date=pub_date,
                            url=uri,
                            doi=doi or '',
                            text=content_text,
                            source_type='open_access',
                            provider_name='HAL Open Science',
                            journal_or_publisher='HAL / CNRS',
                            access_limitations='Open Access (HAL Repository)'
                        ))
        except Exception as e:
            logger.debug(f"HAL search error: {e}")

        return results
