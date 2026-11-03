"""
Connector for the Internet Archive and Wayback Machine.
Queries over 800 billion archived web pages, digitized books, and public domain texts.
"""
from datetime import datetime
import logging
from typing import List, Optional
import requests

from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class InternetArchiveConnector(BaseSourceConnector):
    """
    Connects to the Internet Archive Search & Metadata API (archive.org/advancedsearch.php).
    Searches historical and archived web pages, open library books, and educational documents.
    """

    @property
    def id(self) -> str:
        return 'internet_archive'

    @property
    def name(self) -> str:
        return 'Internet Archive & Wayback Machine'

    @property
    def source_type(self) -> str:
        return 'web'

    @property
    def description(self) -> str:
        return 'Internet Archive global digital repository containing 800B+ archived web pages, books, and public documents.'

    @property
    def supports_full_text(self) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 3:
            return []

        search_query = ' '.join(query_text.split()[:8])
        url = 'https://archive.org/advancedsearch.php'
        params = {
            'q': f'({search_query}) AND (mediatype:texts OR mediatype:web)',
            'fl[]': 'identifier,title,creator,description,publicdate,downloads',
            'sort[]': 'downloads desc',
            'rows': max_results,
            'output': 'json',
        }
        headers = {
            'User-Agent': 'ProovexaSimilarityEngine/2.0 (mailto:archive-integrity@proovexa.com)'
        }

        results = []
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=6.0)
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get('response', {}).get('docs', [])
                for doc in docs:
                    title = doc.get('title', '')
                    identifier = doc.get('identifier', '')
                    creator = doc.get('creator', '')
                    creator_str = ', '.join(creator) if isinstance(creator, list) else str(creator or '')
                    desc = doc.get('description', '')
                    desc_str = ' '.join(desc) if isinstance(desc, list) else str(desc or '')
                    archive_url = f"https://archive.org/details/{identifier}" if identifier else "https://archive.org"

                    pub_date_str = doc.get('publicdate')
                    pub_date = None
                    if pub_date_str:
                        try:
                            pub_date = datetime.strptime(pub_date_str[:10], '%Y-%m-%d').date()
                        except (ValueError, TypeError):
                            pass

                    content_text = desc_str or title

                    if title:
                        results.append(SourceProviderResult(
                            title=title,
                            author=creator_str,
                            publication_date=pub_date,
                            url=archive_url,
                            doi='',
                            text=content_text,
                            source_type='web',
                            provider_name='Internet Archive',
                            journal_or_publisher='Internet Archive',
                            access_limitations='Archived Web / Public Domain'
                        ))
        except Exception as e:
            logger.debug(f"Internet Archive search error: {e}")

        return results
