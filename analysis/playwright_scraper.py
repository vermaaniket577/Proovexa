"""
Playwright-Powered Web Plagiarism Detection & Deep Source Scraper.
=================================================================
Automated live web search and webpage extraction engine using Playwright headless Chromium.

Features:
1. Intelligent Query Synthesizer:
   Extracts distinctive 14+ word academic sentences across the document.
2. Headless Browser Web Crawler:
   Executes live search queries against web and academic indices via Playwright.
3. DOM Text Extractor:
   Navigates to candidate URLs, executes in-page evaluation to strip boilerplate
   (navbars, scripts, advertisements, footers), and extracts clean content.
4. Color-Coded Attribution:
   Pairs every discovered source with Turnitin-compliant hexadecimal color codes.
"""
from __future__ import annotations
import base64
import logging
import re
import urllib.parse
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from django.utils import timezone
from documents.models import ReferenceSource

logger = logging.getLogger(__name__)

# Standard Turnitin 16-color signature palette
TURNITIN_COLOR_PALETTE = [
    ('#E91E63', '#FCE4EC', '#FCE4EC', '#BE185D'),  # 1: Magenta / Pink
    ('#1976D2', '#E3F2FD', '#E0F2FE', '#0369A1'),  # 2: Royal Blue
    ('#2E7D32', '#E8F5E9', '#DCFCE7', '#15803D'),  # 3: Forest Green
    ('#7B1FA2', '#F3E5F5', '#F3E8FF', '#7E22CE'),  # 4: Deep Purple
    ('#C2185B', '#FCE4EC', '#FCE4EC', '#BE185D'),  # 5: Rose
    ('#0288D1', '#E1F5FE', '#E0F2FE', '#0284C7'),  # 6: Sky Blue
    ('#00897B', '#E0F2F1', '#CCFBF1', '#0F766E'),  # 7: Teal
    ('#5E35B1', '#EDE7F6', '#EDE9FE', '#6D28D9'),  # 8: Violet
    ('#D81B60', '#FCE4EC', '#FCE4EC', '#BE185D'),  # 9: Ruby Magenta
    ('#0D47A1', '#E8EAF6', '#E0E7FF', '#1D4ED8'),  # 10: Navy
    ('#EC407A', '#F8BBD0', '#FCE4EC', '#BE185D'),  # 11: Soft Pink
    ('#1565C0', '#BBDEFB', '#E0F2FE', '#1D4ED8'),  # 12: Classic Blue
    ('#00695C', '#B2DFDB', '#D1FAE5', '#047857'),  # 13: Pine Green
    ('#E65100', '#FFF3E0', '#FFEDD5', '#C2410C'),  # 14: Burnt Orange
    ('#4E342E', '#EFEBE9', '#F3F4F6', '#4B5563'),  # 15: Warm Umber
    ('#37474F', '#ECEFF1', '#F1F5F9', '#334155'),  # 16: Slate Grey
]


def get_source_color(source_index: int) -> Tuple[str, str, str, str]:
    """
    Returns (color_code, pastel_bg, pill_bg, pill_text) for a 1-based source index.
    """
    idx = max(1, int(source_index or 1))
    return TURNITIN_COLOR_PALETTE[(idx - 1) % len(TURNITIN_COLOR_PALETTE)]


class PlaywrightPlagiarismChecker:
    """
    Live Internet search and webpage scraper using Playwright to detect
    real-world plagiarism matches from web sources.
    """

    USER_AGENT = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    )

    def __init__(self, headless: bool = True, timeout_ms: int = 12000):
        self.headless = headless
        self.timeout_ms = timeout_ms

    def extract_search_queries(self, full_text: str, min_words: int = 14, max_queries: int = 4) -> List[str]:
        """
        Extracts distinctive, candidate academic sentences (>= min_words)
        from across the document for web similarity verification.
        """
        if not full_text or len(full_text.split()) < min_words:
            return []

        # Split into sentence candidates
        raw_sentences = re.split(r'(?<=[.!?])\s+', full_text)
        candidates = []

        ignore_patterns = [
            re.compile(r'^(table|figure|references|bibliography|abstract|contents|chapter)\b', re.IGNORECASE),
            re.compile(r'^\s*[\d\.\-\*#]+\s*$'),
            re.compile(r'(all rights reserved|copyright|licensed under|et al\.)', re.IGNORECASE),
        ]

        for s in raw_sentences:
            s_clean = s.strip()
            words = s_clean.split()
            # Must meet minimum word count threshold
            if len(words) < min_words or len(words) > 50:
                continue

            # Ignore table captions, bibliography lines, or standard headers
            if any(p.search(s_clean) for p in ignore_patterns):
                continue

            # Skip sentences with too many numbers or special characters
            alpha_ratio = sum(c.isalpha() or c.isspace() for c in s_clean) / max(len(s_clean), 1)
            if alpha_ratio < 0.75:
                continue

            candidates.append(s_clean)

        if not candidates:
            return []

        # Sample evenly across the document (beginning, middle, end)
        if len(candidates) <= max_queries:
            return candidates

        step = max(1, len(candidates) // max_queries)
        sampled = [candidates[i] for i in range(0, len(candidates), step)[:max_queries]]
        return sampled

    def search_and_retrieve_sources(
        self,
        full_text: str,
        min_words: int = 14,
        max_sources: int = 5,
        target_document=None
    ) -> List[ReferenceSource]:
        """
        Executes live web search using Playwright in a dedicated worker thread,
        scrapes candidate webpages, and creates/retrieves ReferenceSource records safely.
        """
        queries = self.extract_search_queries(full_text, min_words=min_words, max_queries=3)
        if not queries:
            logger.info("Playwright checker: No qualifying query sentences found.")
            return []

        # Run Playwright in an isolated thread to keep Django ORM out of Playwright's asyncio loop
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

        harvested_pages: List[Dict[str, Any]] = []
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    self._harvest_pages_worker,
                    queries=queries,
                    max_sources=max_sources,
                    timeout_ms=self.timeout_ms,
                    headless=self.headless,
                    user_agent=self.USER_AGENT,
                )
                # Hard timeout: 30 seconds max to prevent blocking analysis pipeline
                harvested_pages = future.result(timeout=30)
        except FuturesTimeoutError:
            logger.warning("Playwright harvest timed out after 30s — continuing without web sources")
        except Exception as e:
            logger.warning(f"Playwright harvest thread encountered error: {e}")

        # Now safely persist/retrieve ReferenceSource records on the Django thread
        retrieved_sources: List[ReferenceSource] = []
        for item in harvested_pages:
            url = item.get('url', '')
            title = item.get('title', '')
            text = item.get('text', '')
            words = item.get('words', len(text.split()))

            if not url or words < min_words * 2:
                continue

            try:
                existing = ReferenceSource.objects.filter(url=url, is_active=True).first()
                if existing and existing.retrieved_text:
                    retrieved_sources.append(existing)
                else:
                    ref = ReferenceSource.objects.create(
                        title=title[:450],
                        source_type=ReferenceSource.SourceType.WEB,
                        url=url[:950],
                        retrieved_text=text,
                        word_count=words,
                        is_active=True,
                        retrieval_timestamp=timezone.now(),
                        access_limitations="Retrieved live via Playwright Chromium headless engine",
                    )
                    retrieved_sources.append(ref)
                    logger.info(f"Playwright: Saved ReferenceSource '{title}' ({words} words)")
            except Exception as db_err:
                logger.warning(f"Could not persist ReferenceSource for '{url}': {db_err}")

        return retrieved_sources

    @classmethod
    def _harvest_pages_worker(
        cls,
        queries: List[str],
        max_sources: int,
        timeout_ms: int,
        headless: bool,
        user_agent: str,
    ) -> List[Dict[str, Any]]:
        """Worker executing Playwright browser actions without any Django ORM calls."""
        from playwright.sync_api import sync_playwright

        discovered_urls: Dict[str, str] = {}
        pages_content: List[Dict[str, Any]] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(user_agent=user_agent)

            # Step 1: Query Bing for distinctive academic passages
            search_page = context.new_page()
            for query in queries:
                if len(discovered_urls) >= max_sources:
                    break

                query_words = query.split()[:12]
                search_term = " ".join(query_words)
                encoded_q = urllib.parse.quote_plus(search_term)
                search_url = f"https://www.bing.com/search?q={encoded_q}"

                try:
                    resp = search_page.goto(search_url, timeout=timeout_ms, wait_until='domcontentloaded')
                    if resp and resp.status == 200:
                        result_elements = search_page.query_selector_all('li.b_algo')
                        for el in result_elements[:3]:
                            link_el = el.query_selector('h2 a')
                            if not link_el:
                                continue
                            href = link_el.get_attribute('href') or ''
                            title = link_el.inner_text().strip()

                            actual_url = cls._decode_bing_url(href)
                            if actual_url and actual_url.startswith('http') and 'bing.com' not in actual_url:
                                if not any(d in actual_url.lower() for d in ['youtube.com', 'facebook.com', 'twitter.com', 'instagram.com']):
                                    discovered_urls[actual_url] = title
                except Exception as q_err:
                    logger.debug(f"Playwright worker search error: {q_err}")

            search_page.close()

            # Step 2: Visit candidate pages and extract clean text
            for url, initial_title in list(discovered_urls.items())[:max_sources]:
                scrape_page = context.new_page()
                try:
                    page_resp = scrape_page.goto(url, timeout=timeout_ms, wait_until='domcontentloaded')
                    if page_resp and page_resp.status in (200, 206, 301, 302):
                        page_title = scrape_page.title() or initial_title or url

                        raw_text = scrape_page.evaluate('''() => {
                            const removals = document.querySelectorAll(
                                'script, style, noscript, nav, footer, header, aside, .ad, .ads, .sidebar, #comments'
                            );
                            removals.forEach(el => el.remove());
                            return document.body ? document.body.innerText : '';
                        }''')

                        cleaned_text = cls._clean_scraped_text(raw_text)
                        words = len(cleaned_text.split())
                        if words >= 28:
                            pages_content.append({
                                'url': url,
                                'title': page_title,
                                'text': cleaned_text,
                                'words': words,
                            })
                except Exception as s_err:
                    logger.debug(f"Playwright worker scrape error for '{url}': {s_err}")
                finally:
                    scrape_page.close()

            browser.close()

        return pages_content

    @staticmethod
    def _decode_bing_url(href: str) -> str:
        """
        Decodes Bing redirect links containing base64 target URLs.
        Example: /ck/a?!...&u=a1aHR0cHM6Ly9leGFtcGxlLmNvbQ... -> https://example.com
        """
        if not href:
            return ""
        if href.startswith('http') and 'bing.com/ck/a' not in href:
            return href

        # Extract 'u' parameter
        parsed = urllib.parse.urlparse(href)
        params = urllib.parse.parse_qs(parsed.query)
        u_val = params.get('u', [''])[0]
        if u_val and len(u_val) > 2 and u_val.startswith('a1'):
            b64_str = u_val[2:]
            padding = len(b64_str) % 4
            if padding:
                b64_str += '=' * (4 - padding)
            try:
                decoded = base64.urlsafe_b64decode(b64_str).decode('utf-8', errors='ignore')
                return decoded
            except Exception:
                pass
        return href

    @staticmethod
    def _clean_scraped_text(text: str) -> str:
        """Cleans extracted webpage text, removing excessive whitespace and junk."""
        if not text:
            return ""
        # Collapse multiple newlines & tabs
        text = re.sub(r'[\r\t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        lines = [line.strip() for line in text.split('\n') if len(line.strip()) > 3]
        return '\n\n'.join(lines)
