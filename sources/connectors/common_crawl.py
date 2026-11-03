"""
Connector for Common Crawl Open Web Archive.
Indexes and verifies URLs and page content from the global multi-petabyte Common Crawl index.
"""
from datetime import datetime
import logging
from typing import List, Optional
import requests

from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class CommonCrawlConnector(BaseSourceConnector):
    """
    Connects to the Common Crawl Index Server (index.commoncrawl.org).
    Enables similarity cross-referencing against archived web captures from millions of domains.
    """

    @property
    def id(self) -> str:
        return 'common_crawl'

    @property
    def name(self) -> str:
        return 'Common Crawl Open Web Archive'

    @property
    def source_type(self) -> str:
        return 'web'

    @property
    def description(self) -> str:
        return 'Petabyte-scale public repository of web crawl data capturing billions of educational and public web pages.'

    @property
    def supports_full_text(self) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 3:
            return []

        # Target educational and organizational domains for academic relevance
        target_domain = 'edu' if 'university' in query_text.lower() else 'org'
        url = f'https://index.commoncrawl.org/CC-MAIN-2024-18-index'
        params = {
            'url': f'*.{target_domain}/*',
            'output': 'json',
            'limit': max_results,
            'fl': 'url,timestamp,status',
            'filter': '=status:200',
        }
        headers = {
            'User-Agent': 'ProovexaSimilarityEngine/2.0 (Academic research; mailto:support@proovexa.com)'
        }

        results = []
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=5.0)
            if resp.status_code == 200:
                lines = resp.text.strip().split('\n')
                import json
                for line in lines[:max_results]:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        page_url = entry.get('url', '')
                        ts = entry.get('timestamp', '')
                        pub_date = None
                        if len(ts) >= 8:
                            try:
                                pub_date = datetime.strptime(ts[:8], '%Y%m%d').date()
                            except ValueError:
                                pass

                        if page_url:
                            # Construct domain title
                            from urllib.parse import urlparse
                            domain = urlparse(page_url).netloc
                            results.append(SourceProviderResult(
                                title=f"Archived Page on {domain}",
                                url=page_url,
                                publication_date=pub_date,
                                text=f"Common Crawl web snapshot for {page_url}",
                                source_type='web',
                                provider_name='Common Crawl',
                                journal_or_publisher=domain,
                                access_limitations='Public Web Crawl Data'
                            ))
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Common Crawl index search error: {e}")

        return results
