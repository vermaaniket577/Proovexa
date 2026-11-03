"""
Internet & Web Search Connector.
Searches public educational web pages, online publications, and repositories using authorized APIs and crawling.
"""
import os
import re
import logging
import requests
from typing import List, Dict, Any
from django.conf import settings
from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class WebSearchConnector(BaseSourceConnector):
    """Connector for Public Web & Search Engine APIs."""

    @property
    def id(self) -> str:
        return 'web_search'

    @property
    def name(self) -> str:
        return 'Web & Internet Sources'

    @property
    def source_type(self) -> str:
        return 'web'

    @property
    def description(self) -> str:
        return (
            "Searches accessible public educational websites, university repositories, government portals, "
            "and indexed internet pages via authorized search APIs and crawling."
        )

    def is_available(self) -> bool:
        return True

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 5:
            return []

        # 1. Try Google Custom Search API if configured
        google_results = self._search_google_api(query_text, max_results=max_results)
        if google_results:
            return google_results

        # 2. Try Bing Web Search API if configured
        bing_results = self._search_bing_api(query_text, max_results=max_results)
        if bing_results:
            return bing_results

        # 3. Fallback: DuckDuckGo Instant Answer and Web topic search
        ddg_results = self._search_duckduckgo(query_text, max_results=max_results)
        if ddg_results:
            return ddg_results

        # 4. Optional Playwright headless crawler if available
        playwright_results = self._search_playwright_fallback(query_text, max_results=max_results)
        return playwright_results

    def _search_google_api(self, query: str, max_results: int = 5) -> List[SourceProviderResult]:
        try:
            from django.conf import settings
            api_key = getattr(settings, 'GOOGLE_SEARCH_API_KEY', os.environ.get('GOOGLE_SEARCH_API_KEY', ''))
            cx = getattr(settings, 'GOOGLE_SEARCH_CX', os.environ.get('GOOGLE_SEARCH_CX', ''))
        except Exception:
            api_key = os.environ.get('GOOGLE_SEARCH_API_KEY', '')
            cx = os.environ.get('GOOGLE_SEARCH_CX', '')
        if not api_key or not cx:
            return []

        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': api_key,
            'cx': cx,
            'q': query[:150],
            'num': min(max_results, 5),
        }
        try:
            resp = requests.get(url, params=params, timeout=6)
            if resp.status_code != 200:
                return []
            items = resp.json().get('items', [])
            results = []
            for item in items:
                title = item.get('title', '')
                snippet = item.get('snippet', '')
                link = item.get('link', '')
                display_link = item.get('displayLink', '')
                results.append(SourceProviderResult(
                    title=title,
                    url=link,
                    text=f"{title}\n{snippet}",
                    source_type='web',
                    provider_name='Google Search',
                    journal_or_publisher=display_link,
                    access_limitations='Google Custom Search API',
                ))
            return results
        except Exception as e:
            logger.debug(f"Google API search failed: {e}")
            return []

    def _search_bing_api(self, query: str, max_results: int = 5) -> List[SourceProviderResult]:
        try:
            from django.conf import settings
            api_key = getattr(settings, 'BING_SEARCH_API_KEY', os.environ.get('BING_SEARCH_API_KEY', ''))
        except Exception:
            api_key = os.environ.get('BING_SEARCH_API_KEY', '')
        if not api_key:
            return []

        url = "https://api.bing.microsoft.com/v7.0/search"
        headers = {'Ocp-Apim-Subscription-Key': api_key}
        params = {'q': query[:150], 'count': min(max_results, 5)}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=6)
            if resp.status_code != 200:
                return []
            web_pages = resp.json().get('webPages', {}).get('value', [])
            results = []
            for item in web_pages:
                title = item.get('name', '')
                snippet = item.get('snippet', '')
                url_str = item.get('url', '')
                results.append(SourceProviderResult(
                    title=title,
                    url=url_str,
                    text=f"{title}\n{snippet}",
                    source_type='web',
                    provider_name='Bing Search',
                    access_limitations='Bing Web Search API',
                ))
            return results
        except Exception as e:
            logger.debug(f"Bing API search failed: {e}")
            return []

    def _search_duckduckgo(self, query: str, max_results: int = 5) -> List[SourceProviderResult]:
        url = "https://api.duckduckgo.com/"
        params = {
            'q': query[:150],
            'format': 'json',
            'no_html': 1,
            'skip_disambig': 1,
        }
        headers = {'User-Agent': 'ProovexaSearch/2.0'}
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=5)
            if resp.status_code != 200:
                return []
            data = resp.json()
            results = []

            # 1. Main Abstract
            heading = data.get('Heading', '')
            abstract = data.get('AbstractText', '')
            abs_url = data.get('AbstractURL', '')
            if heading and abstract:
                results.append(SourceProviderResult(
                    title=heading,
                    url=abs_url,
                    text=f"{heading}\n{abstract}",
                    source_type='web',
                    provider_name='DuckDuckGo Search',
                    journal_or_publisher=data.get('AbstractSource', 'Web'),
                    access_limitations='DuckDuckGo Instant Answer API',
                ))

            # 2. Related Topics
            for topic in data.get('RelatedTopics', []):
                if len(results) >= max_results:
                    break
                t_text = topic.get('Text', '')
                t_url = topic.get('FirstURL', '')
                if t_text and t_url:
                    results.append(SourceProviderResult(
                        title=t_text[:80],
                        url=t_url,
                        text=t_text,
                        source_type='web',
                        provider_name='DuckDuckGo Search',
                        access_limitations='DuckDuckGo Instant Answer API',
                    ))

            return results
        except Exception as e:
            logger.debug(f"DuckDuckGo search error: {e}")
            return []

    def _search_playwright_fallback(self, query: str, max_results: int = 3) -> List[SourceProviderResult]:
        try:
            from django.conf import settings
            enable_pw = getattr(settings, 'ENABLE_PLAYWRIGHT_SEARCH', False)
        except Exception:
            enable_pw = False
        if not enable_pw:
            return []

        try:
            from analysis.playwright_scraper import PlaywrightPlagiarismChecker
            checker = PlaywrightPlagiarismChecker(headless=True, timeout_ms=4000)
            sources = checker.search_and_retrieve_sources(full_text=query, max_sources=max_results)
            results = []
            for s in sources:
                results.append(SourceProviderResult(
                    title=s.title,
                    author=s.author,
                    url=s.url,
                    doi=s.doi,
                    text=s.retrieved_text,
                    source_type='web',
                    provider_name='Web Crawler',
                    access_limitations=s.access_limitations,
                ))
            return results
        except Exception:
            return []

    def get_rate_limit_info(self) -> dict:
        has_google = bool(getattr(settings, 'GOOGLE_SEARCH_API_KEY', os.environ.get('GOOGLE_SEARCH_API_KEY', '')))
        has_bing = bool(getattr(settings, 'BING_SEARCH_API_KEY', os.environ.get('BING_SEARCH_API_KEY', '')))
        return {
            'rate_limit': 'Google (100 free queries/day), Bing (Free tier 1k/month), DuckDuckGo (Open)',
            'terms_url': 'https://developers.google.com/custom-search/v1/overview',
            'license_info': 'Authorized Search Engine API integration',
            'has_google_key': has_google,
            'has_bing_key': has_bing,
        }
