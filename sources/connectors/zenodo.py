"""
Connector for Zenodo REST API.
CERN-developed open science repository for European research and multidisciplinary publications.
"""
from datetime import datetime
import logging
import re
from typing import List, Optional
import requests

from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class ZenodoConnector(BaseSourceConnector):
    """
    Connects to the official Zenodo REST API (zenodo.org/api/records).
    Covers open access papers, preprints, dissertations, and scientific datasets.
    """

    @property
    def id(self) -> str:
        return 'zenodo'

    @property
    def name(self) -> str:
        return 'Zenodo (CERN / OpenAIRE)'

    @property
    def source_type(self) -> str:
        return 'open_access'

    @property
    def description(self) -> str:
        return 'CERN and OpenAIRE multidisciplinary repository for global scholarly research, theses, and publications.'

    @property
    def supports_full_text(self) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 3:
            return []

        search_query = ' '.join(query_text.split()[:10])
        url = 'https://zenodo.org/api/records'
        params = {
            'q': search_query,
            'size': max_results,
            'status': 'published',
            'sort': 'bestmatch',
        }
        headers = {
            'User-Agent': 'ProovexaSimilarityEngine/2.0 (Academic research; mailto:support@proovexa.com)'
        }

        results = []
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=6.0)
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get('hits', {}).get('hits', [])
                for hit in hits:
                    metadata = hit.get('metadata', {})
                    title = metadata.get('title', '')
                    raw_desc = metadata.get('description', '')
                    # Clean HTML tags from description
                    clean_desc = re.sub(r'<[^>]+>', ' ', raw_desc).strip()
                    creators = metadata.get('creators', [])
                    author_names = ', '.join(c.get('name', '') for c in creators if c.get('name'))
                    doi = hit.get('doi', metadata.get('doi', ''))
                    rec_id = hit.get('id', '')
                    rec_url = hit.get('links', {}).get('html', f"https://zenodo.org/records/{rec_id}" if rec_id else "")

                    pub_date_str = metadata.get('publication_date')
                    pub_date = None
                    if pub_date_str:
                        try:
                            pub_date = datetime.strptime(pub_date_str[:10], '%Y-%m-%d').date()
                        except (ValueError, TypeError):
                            pass

                    content_text = clean_desc or title

                    if title:
                        results.append(SourceProviderResult(
                            title=title,
                            author=author_names,
                            publication_date=pub_date,
                            url=rec_url,
                            doi=doi,
                            text=content_text,
                            source_type='open_access',
                            provider_name='Zenodo',
                            journal_or_publisher='Zenodo / CERN',
                            access_limitations='Creative Commons / Open Access'
                        ))
        except Exception as e:
            logger.debug(f"Zenodo search error: {e}")

        return results
