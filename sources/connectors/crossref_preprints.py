"""
Connector for Crossref Posted Content (Preprints and Working Papers).
Retrieves scholarly preprints from bioRxiv, medRxiv, ChemRxiv, Research Square, Authorea, and SSRN.
"""
from datetime import datetime
import logging
from typing import List, Optional
import requests

from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class CrossrefPreprintsConnector(BaseSourceConnector):
    """
    Connects to Crossref REST API filtering specifically for type:posted-content (preprints).
    """

    @property
    def id(self) -> str:
        return 'crossref_preprints'

    @property
    def name(self) -> str:
        return 'Crossref Posted Content (Preprints & Working Papers)'

    @property
    def source_type(self) -> str:
        return 'academic'

    @property
    def description(self) -> str:
        return 'Preprint servers indexed by Crossref including bioRxiv, medRxiv, ChemRxiv, Research Square, and SSRN.'

    @property
    def supports_full_text(self) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 3:
            return []

        search_query = ' '.join(query_text.split()[:10])
        url = 'https://api.crossref.org/works'
        params = {
            'query.bibliographic': search_query,
            'filter': 'type:posted-content',
            'rows': max_results,
            'select': 'DOI,title,author,published-print,published-online,URL,abstract,publisher,subtype',
        }
        headers = {
            'User-Agent': 'ProovexaSimilarityEngine/2.0 (mailto:academic-integrity@proovexa.com)'
        }

        results = []
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=6.0)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('message', {}).get('items', [])
                for it in items:
                    titles = it.get('title', [])
                    title = titles[0] if titles else ''
                    doi = it.get('DOI', '')
                    item_url = it.get('URL', f"https://doi.org/{doi}" if doi else '')
                    publisher = it.get('publisher', 'Preprint Server')
                    abstract = it.get('abstract', '')
                    if abstract and abstract.startswith('<jats:p>'):
                        import re
                        abstract = re.sub(r'<[^>]+>', ' ', abstract).strip()

                    author_list = []
                    for a in it.get('author', []):
                        fn = a.get('given', '')
                        ln = a.get('family', '')
                        full = f"{fn} {ln}".strip()
                        if full:
                            author_list.append(full)
                    author_str = ', '.join(author_list)

                    if title:
                        results.append(SourceProviderResult(
                            title=title,
                            author=author_str,
                            url=item_url,
                            doi=doi,
                            text=abstract or title,
                            source_type='academic',
                            provider_name='Crossref Preprints',
                            journal_or_publisher=publisher,
                            access_limitations='Preprint / Open Access'
                        ))
        except Exception as e:
            logger.debug(f"Crossref preprints search error: {e}")

        return results
