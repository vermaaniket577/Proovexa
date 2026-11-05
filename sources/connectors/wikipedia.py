"""
Wikipedia Open Knowledge Connector.
https://www.wikipedia.org/ - Authoritative public educational encyclopedia text across millions of topics.
"""
import logging
import requests
from typing import List
from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class WikipediaConnector(BaseSourceConnector):
    """Connector for Wikipedia Search & Full-Extract API."""

    @property
    def id(self) -> str:
        return 'wikipedia'

    @property
    def name(self) -> str:
        return 'Wikipedia'

    @property
    def source_type(self) -> str:
        return 'web'

    @property
    def description(self) -> str:
        return (
            "Open collaborative encyclopedia containing over 60+ million referenced articles "
            "across 300+ languages."
        )

    def is_available(self) -> bool:
        return True

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 4:
            return []

        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            'action': 'query',
            'list': 'search',
            'srsearch': query_text.strip()[:180],
            'format': 'json',
            'utf8': 1,
            'srlimit': min(max_results, 5),
        }
        headers = {'User-Agent': 'ProovexaSimilarityEngine/2.0 (mailto:admin@proovexa.edu)'}

        try:
            resp = requests.get(search_url, params=search_params, headers=headers, timeout=6)
            if resp.status_code != 200:
                return []

            search_items = resp.json().get('query', {}).get('search', [])
            if not search_items:
                return []

            results = []
            titles = [item['title'] for item in search_items[:max_results]]

            # Fetch plain-text extracts in batch (fast intro extracts)
            extract_params = {
                'action': 'query',
                'prop': 'extracts|info',
                'exintro': 1,
                'explaintext': 1,
                'inprop': 'url',
                'titles': "|".join(titles),
                'format': 'json',
                'utf8': 1,
            }
            ext_resp = requests.get(search_url, params=extract_params, headers=headers, timeout=6)
            if ext_resp.status_code != 200:
                return []

            pages = ext_resp.json().get('query', {}).get('pages', {})
            for pid, page in pages.items():
                title = page.get('title', '').strip()
                extract = page.get('extract', '').strip()
                page_url = page.get('fullurl', f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}")

                if not title or not extract:
                    continue

                content_text = f"{title}\n\n{extract}"

                results.append(SourceProviderResult(
                    title=f"Wikipedia: {title}",
                    author="Wikipedia Contributors",
                    url=page_url,
                    text=content_text,
                    source_type='web',
                    provider_name='Wikipedia',
                    journal_or_publisher='Wikimedia Foundation',
                    access_limitations='Creative Commons Attribution-ShareAlike (CC BY-SA 4.0)',
                ))

            return results
        except Exception as e:
            logger.warning(f"Wikipedia search exception: {e}")
            return []

    def get_rate_limit_info(self) -> dict:
        return {
            'rate_limit': 'Up to 200 requests/second with User-Agent header',
            'terms_url': 'https://www.mediawiki.org/wiki/API:Etiquette',
            'license_info': 'Creative Commons Attribution-ShareAlike 4.0',
        }
