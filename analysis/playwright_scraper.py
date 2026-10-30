"""
Playwright-Powered Web Plagiarism Detection & Deep Source Scraper.
=================================================================
Automated live web search and webpage extraction engine using Playwright headless Chromium.

Features:
1. Intelligent Title & Query Synthesizer:
   Extracts exact paper titles and prominent distinctive sentences across the document.
2. Google Search & Web Crawler:
   Actively searches the paper's title on Google Search Engine (with automated multi-engine
   fallbacks) to discover indexed publications, preprint servers, and academic repositories.
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
from typing import List, Dict, Any, Optional, Tuple, Set

from django.utils import timezone
from documents.models import ReferenceSource

logger = logging.getLogger(__name__)

# Standard Turnitin 16-color signature palette: (badge_solid, pastel_bg, pill_bg, pill_text)
TURNITIN_COLOR_PALETTE = [
    ('#e91e63', '#fce4ec', '#fce4ec', '#191919'),  # 1: Magenta / Pink
    ('#1976d2', '#e3f2fd', '#e0f2fe', '#191919'),  # 2: Royal Blue
    ('#2e7d32', '#e8f5e9', '#dcfce7', '#191919'),  # 3: Forest Green
    ('#7b1fa2', '#f3e5f5', '#ede9fe', '#191919'),  # 4: Deep Purple
    ('#c2185b', '#fce4ec', '#fce7f3', '#191919'),  # 5: Rose
    ('#0288d1', '#e1f5fe', '#e0f2fe', '#191919'),  # 6: Sky Blue
    ('#00897b', '#e0f2f1', '#ccfbf1', '#191919'),  # 7: Teal
    ('#5e35b1', '#ede7f6', '#ede9fe', '#191919'),  # 8: Violet
    ('#d81b60', '#fce4ec', '#ffe4e6', '#191919'),  # 9: Ruby Magenta
    ('#0d47a1', '#e8eaf6', '#e0f2fe', '#191919'),  # 10: Navy
    ('#ec407a', '#f8bbd0', '#fce4ec', '#191919'),  # 11: Soft Pink
    ('#1565c0', '#bbdefb', '#e0f2fe', '#191919'),  # 12: Classic Blue
    ('#00695c', '#b2dfdb', '#d1fae5', '#191919'),  # 13: Pine Green
    ('#e65100', '#fff3e0', '#ffedd5', '#191919'),  # 14: Burnt Orange
    ('#4e342e', '#efebe9', '#f3f4f6', '#191919'),  # 15: Warm Umber
    ('#37474f', '#eceff1', '#f1f5f9', '#191919'),  # 16: Slate Grey
]


def get_source_color(source_index: int) -> Tuple[str, str, str, str]:
    """
    Returns (color_code, pastel_bg, pill_bg, pill_text) for a 1-based source index.
    """
    idx = max(1, int(source_index or 1))
    return TURNITIN_COLOR_PALETTE[(idx - 1) % len(TURNITIN_COLOR_PALETTE)]


def _clean_tokens(title: str) -> Set[str]:
    """Extracts meaningful alphabetic words from a title string, ignoring stopwords."""
    STOPWORDS = {
        'the', 'a', 'an', 'in', 'on', 'of', 'and', 'or', 'for', 'to', 'with', 'at',
        'by', 'from', 'as', 'is', 'are', 'was', 'were', 'it', 'its', 'pdf', 'doi',
        'paper', 'report', 'review', 'study', 'analysis', 'journal', 'com', 'org',
        'edu', 'www', 'http', 'https'
    }
    words = re.findall(r'[a-zA-Z0-9]+', title.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def _strip_site_suffix(title: str) -> str:
    """Strips common website branding and leading brackets from titles."""
    if not title:
        return ""
    # Strip leading brackets e.g. [1706.03762], (PDF)
    title = re.sub(r'^\s*\[[^\]]+\]\s*', '', title)
    title = re.sub(r'^\s*\([^\)]+\)\s*', '', title)
    # Strip trailing site prefixes/suffixes e.g. " - arXiv", " | ResearchGate", " - Wikipedia"
    title = re.sub(
        r'\s*[\-|–|—|•|\|]\s*(arXiv|Wikipedia|ResearchGate|ScienceDirect|SpringerLink|IEEE|Emerald|JSTOR|PubMed|Google Scholar|Semantic Scholar|Wiley|Taylor & Francis|PLOS|Frontiers|Nature|MDPI|Sage|BioMed Central).*$',
        '', title, flags=re.IGNORECASE
    )
    # Strip trailing generic " | ... " or " - ..." if it's a domain or short site name
    title = re.sub(r'\s+[\|\-–—]\s+[A-Za-z0-9\.\s]{2,25}$', '', title)
    return title.strip()


def _is_title_match(candidate_title: str, paper_titles: List[str]) -> bool:
    """
    Determines if candidate webpage title has significant overlap with the paper's title.
    """
    if not candidate_title or not paper_titles:
        return False

    clean_candidate = _strip_site_suffix(candidate_title)
    c_norm = re.sub(r'\s+', ' ', re.sub(r'[^a-zA-Z0-9\s]', '', clean_candidate.lower())).strip()
    c_tokens = _clean_tokens(clean_candidate)

    for p in paper_titles:
        if not p:
            continue
        p_clean = _strip_site_suffix(p)
        p_norm = re.sub(r'\s+', ' ', re.sub(r'[^a-zA-Z0-9\s]', '', p_clean.lower())).strip()
        # Direct substring containment
        if p_norm and (p_norm in c_norm or c_norm in p_norm):
            return True

        p_tokens = _clean_tokens(p_clean)
        if not p_tokens or not c_tokens:
            continue
        overlap = len(p_tokens.intersection(c_tokens))
        ratio = overlap / min(len(p_tokens), len(c_tokens))
        if ratio >= 0.30:  # Overlap >= 30% of substantive keywords
            return True

    return False


def extract_paper_titles(target_document=None, full_text: str = "") -> List[str]:
    """
    Extracts candidate academic paper titles from both document metadata and the document body text.
    Handles standard uploads, drafts, as well as documents with Turnitin/cover sheet pages.
    """
    titles: List[str] = []

    def _clean_str(raw: str) -> str:
        if not raw:
            return ""
        c = re.sub(r'\.(docx|pdf|doc|txt|rtf|odt)$', '', raw, flags=re.IGNORECASE)
        c = re.sub(r'[_\-]+', ' ', c)
        c = re.sub(r'\s*\(\d+\)\s*', ' ', c)
        c = re.sub(r'\b\d{1,2}[\.\-\/]\d{1,2}[\.\-\/]\d{2,4}\b', '', c)
        c = re.sub(r'\b(final|corrected|paper|revised|yellow|highlights|synopsis|template|draft|v\d+)\b', '', c, flags=re.IGNORECASE)
        return ' '.join(c.split())

    # 1. From document title & original filename
    if target_document:
        for attr in ['title', 'original_filename']:
            raw = getattr(target_document, attr, None) or ""
            cleaned = _clean_str(raw)
            if cleaned and len(cleaned) >= 4 and cleaned not in titles:
                titles.append(cleaned)

    # 2. Extract from full text
    if full_text:
        # Check for metadata headers like "File Name: ...", "Title: ..." in the first 4000 characters
        fn_match = re.search(r'(?:File Name|Title)\s*[:\s]\s*([A-Za-z0-9_\-\.\s]+?\.(?:docx|pdf|doc|txt))', full_text[:4000], re.IGNORECASE)
        if fn_match:
            c = _clean_str(fn_match.group(1))
            if c and len(c) >= 4 and c not in titles:
                titles.append(c)

        # Detect and skip cover / Turnitin overview sheet if present
        text_for_headings = full_text
        cover_indicators = ['submission id', 'turnitin', 'document details', 'integrity overview', 'page 1 of']
        if any(ind in full_text[:1500].lower() for ind in cover_indicators):
            sub_start = re.search(r'Integrity Submission[^\n]*\n+', full_text, re.IGNORECASE)
            if sub_start:
                text_for_headings = full_text[sub_start.end():]
            else:
                text_for_headings = full_text[2500:]

        # Check the first paragraph/lines for the main heading before "Abstract", "Introduction", etc.
        first_chunk = text_for_headings[:4000]
        abs_split = re.split(r'\b(?:Abstract|Introduction|Keywords|Purpose:)\b', first_chunk, flags=re.IGNORECASE)
        if len(abs_split) > 1 and abs_split[0].strip():
            candidate_line = abs_split[0].strip()
            sub_lines = [l.strip() for l in candidate_line.split('\n') if l.strip()]
            for sl in reversed(sub_lines):
                words = sl.split()
                if 3 <= len(words) <= 28 and 12 <= len(sl) <= 220:
                    clean_t = ' '.join(sl.split())
                    if clean_t not in titles:
                        titles.append(clean_t)
                    break

        # Also scan top lines of text_for_headings
        lines = [l.strip() for l in text_for_headings[:3500].split('\n') if l.strip()]
        ignore_prefixes = (
            'page ', 'abstract', 'table of contents', 'contents', 'chapter', 'author', 'issn', 'doi',
            'department', 'faculty', 'university', 'journal', 'volume', 'issue', 'submitted', 'date',
            'fig.', 'figure', 'table', 'keywords', 'introduction', 'references', 'works cited'
        )

        for l in lines[:15]:
            l_lower = l.lower()
            if any(l_lower.startswith(p) for p in ignore_prefixes):
                continue
            words = l.split()
            if 3 <= len(words) <= 28 and 12 <= len(l) <= 220:
                alpha_ratio = sum(c.isalpha() or c.isspace() for c in l) / max(len(l), 1)
                if alpha_ratio >= 0.70:
                    clean_text_title = ' '.join(l.split())
                    if clean_text_title not in titles:
                        titles.append(clean_text_title)
                    break

    return titles


class PlaywrightPlagiarismChecker:
    """
    Live Google Search and deep webpage scraper using Playwright to detect
    real-world plagiarism matches from indexed web sources.
    """

    USER_AGENT = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/126.0.0.0 Safari/537.36'
    )

    def __init__(self, headless: bool = True, timeout_ms: int = 12000):
        self.headless = headless
        self.timeout_ms = timeout_ms

    def extract_search_queries(
        self,
        full_text: str,
        paper_titles: List[str] = None,
        min_words: int = 14,
        max_queries: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Synthesizes high-precision search queries:
        1. Exact and broad queries for the paper's title in Google Search.
        2. Distinctive academic body sentences (>= min_words).
        """
        queries: List[Dict[str, Any]] = []

        # Step 1: Paper Title Queries (Highest Priority for Google Search)
        if paper_titles:
            for title in paper_titles:
                clean_t = title.strip()
                if len(clean_t) >= 6:
                    # Exact quoted search
                    queries.append({
                        'query': f'"{clean_t}"',
                        'type': 'title_exact',
                        'raw_title': clean_t
                    })
                    # Broad search without quotes
                    queries.append({
                        'query': clean_t,
                        'type': 'title_broad',
                        'raw_title': clean_t
                    })
                    break

        # Step 2: Distinctive body sentence queries
        if full_text and len(full_text.split()) >= min_words:
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
                if len(words) < min_words or len(words) > 50:
                    continue
                if any(p.search(s_clean) for p in ignore_patterns):
                    continue
                alpha_ratio = sum(c.isalpha() or c.isspace() for c in s_clean) / max(len(s_clean), 1)
                if alpha_ratio < 0.75:
                    continue
                candidates.append(s_clean)

            if candidates:
                step = max(1, len(candidates) // 2)
                for i in range(0, len(candidates), step)[:2]:
                    sentence_snippet = " ".join(candidates[i].split()[:14])
                    queries.append({
                        'query': sentence_snippet,
                        'type': 'sentence',
                        'raw_title': ''
                    })

        return queries[:max_queries + 2]

    def search_and_retrieve_sources(
        self,
        full_text: str,
        min_words: int = 14,
        max_sources: int = 8,
        target_document=None
    ) -> List[ReferenceSource]:
        """
        Searches the paper's title and key passages on Google Search Engine using Playwright,
        crawls all matching candidate pages, and saves them as ReferenceSource records.
        """
        paper_titles = extract_paper_titles(target_document, full_text)
        queries = self.extract_search_queries(
            full_text=full_text,
            paper_titles=paper_titles,
            min_words=min_words,
            max_queries=4
        )

        if not queries:
            logger.info("Playwright checker: No qualifying title or query sentences found.")
            return []

        logger.info(f"Playwright: Extracted paper titles: {paper_titles}. Generated {len(queries)} search queries.")

        # Run Playwright in an isolated thread
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

        harvested_pages: List[Dict[str, Any]] = []
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    self._harvest_pages_worker,
                    queries=queries,
                    paper_titles=paper_titles,
                    max_sources=max_sources,
                    timeout_ms=self.timeout_ms,
                    headless=self.headless,
                    user_agent=self.USER_AGENT,
                )
                harvested_pages = future.result(timeout=50)
        except FuturesTimeoutError:
            logger.warning("Playwright harvest timed out after 50s — continuing with partial web sources")
        except Exception as e:
            logger.warning(f"Playwright harvest thread encountered error: {e}")

        # Now safely persist/retrieve ReferenceSource records on the Django thread
        retrieved_sources: List[ReferenceSource] = []
        for item in harvested_pages:
            url = item.get('url', '')
            title = item.get('title', '')
            text = item.get('text', '')
            words = item.get('words', len(text.split()))

            if not url or words < 25:
                continue

            try:
                existing = ReferenceSource.objects.filter(url=url, is_active=True).first()
                if existing:
                    if not existing.retrieved_text or len(existing.retrieved_text) < len(text):
                        existing.retrieved_text = text
                        existing.word_count = words
                        existing.save(update_fields=['retrieved_text', 'word_count'])
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
                        access_limitations="Retrieved live via Google Search Engine Playwright crawler",
                    )
                    retrieved_sources.append(ref)
                    logger.info(f"Playwright: Saved ReferenceSource '{title}' ({words} words) from {url}")
            except Exception as db_err:
                logger.warning(f"Could not persist ReferenceSource for '{url}': {db_err}")

        return retrieved_sources

    @classmethod
    def _harvest_pages_worker(
        cls,
        queries: List[Dict[str, Any]],
        paper_titles: List[str],
        max_sources: int,
        timeout_ms: int,
        headless: bool,
        user_agent: str,
    ) -> List[Dict[str, Any]]:
        """Worker executing Playwright browser actions for Google Search and webpage crawling."""
        from playwright.sync_api import sync_playwright

        discovered_urls: Dict[str, str] = {}
        pages_content: List[Dict[str, Any]] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )
            context = browser.new_context(
                user_agent=user_agent,
                locale="en-US"
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")

            # -------------------------------------------------------------
            # STEP 1: Search Queries across Google (Primary) & Fallback Engines
            # -------------------------------------------------------------
            for q_item in queries:
                if len(pages_content) >= max_sources or len(discovered_urls) >= max_sources * 3:
                    break

                q_str = q_item['query']
                q_type = q_item['type']
                logger.info(f"Playwright: Searching query [{q_type}]: '{q_str}'")

                # Strategy 1: Google Search
                try:
                    search_page = context.new_page()
                    search_page.goto("https://www.google.com", timeout=12000, wait_until="domcontentloaded")

                    # Handle Google consent dialogs
                    for btn_text in ["Accept all", "Reject all", "I agree", "#L2AGLb", "#W0wltc"]:
                        try:
                            btn = search_page.query_selector(f"button:has-text('{btn_text}')" if not btn_text.startswith('#') else btn_text)
                            if btn:
                                btn.click()
                                search_page.wait_for_timeout(600)
                                break
                        except Exception:
                            pass

                    search_box = search_page.query_selector("textarea[name='q'], input[name='q']")
                    if search_box:
                        search_box.fill(q_str)
                        search_page.keyboard.press("Enter")
                        search_page.wait_for_timeout(2500)

                        google_cards = search_page.query_selector_all("a:has(h3)")
                        for card in google_cards:
                            h3 = card.query_selector("h3")
                            title = h3.inner_text().strip() if h3 else ""
                            if not title or "AI Mode" in title:
                                continue

                            raw_href = card.get_attribute("href") or ""
                            if not raw_href:
                                continue

                            # Resolve Google redirect or direct link
                            target_url = ""
                            if "google.com/url?" in raw_href or raw_href.startswith("/url?"):
                                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
                                q_val = parsed.get("q", [""])[0] or parsed.get("url", [""])[0]
                                if q_val.startswith("http"):
                                    target_url = q_val
                            elif raw_href.startswith("http") and "google.com" not in raw_href:
                                target_url = raw_href

                            # Check if title matches or top result
                            is_match = True
                            if q_type.startswith("title"):
                                is_match = _is_title_match(title, paper_titles) or len(discovered_urls) < 3

                            if is_match:
                                if target_url:
                                    discovered_urls[target_url] = title
                                elif raw_href.startswith("/goto?url=") or "google.com/goto?url=" in raw_href:
                                    # Directly crawl Google redirect card
                                    if len(pages_content) < max_sources:
                                        full_goto = f"https://www.google.com{raw_href}" if raw_href.startswith("/") else raw_href
                                        scrape_p = context.new_page()
                                        try:
                                            scrape_p.goto(full_goto, timeout=timeout_ms, wait_until="domcontentloaded")
                                            scrape_p.wait_for_timeout(1000)
                                            landed_url = scrape_p.url
                                            landed_title = scrape_p.title() or title
                                            if landed_url and "google.com" not in landed_url:
                                                raw_text = scrape_p.evaluate('''() => {
                                                    const removals = document.querySelectorAll(
                                                        'script, style, noscript, nav, footer, header, aside, .ad, .ads, .sidebar, #comments, .cookie-banner, .modal'
                                                    );
                                                    removals.forEach(el => el.remove());
                                                    return document.body ? document.body.innerText : '';
                                                }''')
                                                cleaned_text = cls._clean_scraped_text(raw_text)
                                                words = len(cleaned_text.split())
                                                if words >= 28 and not any(p['url'] == landed_url for p in pages_content):
                                                    pages_content.append({
                                                        'url': landed_url,
                                                        'title': landed_title[:400],
                                                        'text': cleaned_text,
                                                        'words': words,
                                                    })
                                                    logger.info(f"Playwright: Crawled from Google search '{landed_title}' ({words} words)")
                                        except Exception as c_err:
                                            logger.debug(f"Google card crawl error: {c_err}")
                                        finally:
                                            scrape_p.close()

                    search_page.close()
                except Exception as g_err:
                    logger.debug(f"Google search error for '{q_str}': {g_err}")

                # Strategy 2: Yahoo Search
                if len(pages_content) < max_sources and len(discovered_urls) < max_sources:
                    try:
                        y_page = context.new_page()
                        y_url = f"https://search.yahoo.com/search?p={urllib.parse.quote_plus(q_str)}"
                        y_page.goto(y_url, timeout=10000, wait_until="domcontentloaded")
                        y_results = y_page.evaluate('''() => {
                            const list = [];
                            document.querySelectorAll('div#web ol li div.compTitle a, h3.title a').forEach(a => {
                                if (a.href && !a.href.includes('yahoo.com')) {
                                    list.push({ title: a.innerText.trim(), href: a.href });
                                }
                            });
                            return list;
                        }''')
                        for r in y_results:
                            href = r.get('href', '')
                            title = r.get('title', '')
                            if href and not any(d in href for d in ['yahoo.com', 'youtube.com', 'facebook.com', 'twitter.com']):
                                if q_type.startswith('title'):
                                    if _is_title_match(title, paper_titles) or len(discovered_urls) < 3:
                                        discovered_urls[href] = title
                                else:
                                    discovered_urls[href] = title
                        y_page.close()
                    except Exception as y_err:
                        logger.debug(f"Yahoo search fallback error for '{q_str}': {y_err}")

                # Strategy 3: Bing Search
                if len(pages_content) < max_sources and len(discovered_urls) < max_sources:
                    try:
                        b_page = context.new_page()
                        b_url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(q_str)}"
                        b_page.goto(b_url, timeout=10000, wait_until="domcontentloaded")
                        b_elements = b_page.query_selector_all('li.b_algo h2 a')
                        for el in b_elements[:5]:
                            href = el.get_attribute('href') or ''
                            title = el.inner_text().strip()
                            actual_url = cls._decode_bing_url(href)
                            if actual_url and actual_url.startswith('http') and 'bing.com' not in actual_url:
                                if not any(d in actual_url.lower() for d in ['youtube.com', 'facebook.com', 'twitter.com']):
                                    if q_type.startswith('title'):
                                        if _is_title_match(title, paper_titles) or len(discovered_urls) < 3:
                                            discovered_urls[actual_url] = title
                                    else:
                                        discovered_urls[actual_url] = title
                        b_page.close()
                    except Exception as b_err:
                        logger.debug(f"Bing search error: {b_err}")

            logger.info(f"Playwright: Total discovered candidate URLs: {len(discovered_urls)}")

            # -------------------------------------------------------------
            # STEP 2: Crawl Discovered URLs & Extract Clean Page Texts
            # -------------------------------------------------------------
            crawled_domains = set()

            for url, initial_title in list(discovered_urls.items()):
                if len(pages_content) >= max_sources:
                    break

                if any(p['url'] == url for p in pages_content):
                    continue

                domain = urllib.parse.urlparse(url).netloc.lower()
                if domain in crawled_domains and len(crawled_domains) >= 3:
                    continue

                # Handle direct PDF URLs via requests + PyMuPDF
                if url.lower().endswith('.pdf'):
                    try:
                        import requests
                        import pymupdf
                        resp = requests.get(url, headers={'User-Agent': user_agent}, timeout=10)
                        if resp.status_code == 200 and resp.content:
                            doc = pymupdf.open(stream=resp.content, filetype='pdf')
                            pdf_text = "\n".join(pg.get_text() for pg in doc[:15])
                            cleaned_text = cls._clean_scraped_text(pdf_text)
                            words = len(cleaned_text.split())
                            if words >= 28:
                                pages_content.append({
                                    'url': url,
                                    'title': initial_title[:400],
                                    'text': cleaned_text,
                                    'words': words,
                                })
                                crawled_domains.add(domain)
                                logger.info(f"Playwright: Successfully crawled PDF '{initial_title}' ({words} words)")
                                continue
                    except Exception as pdf_err:
                        logger.debug(f"PDF crawl error for {url}: {pdf_err}")

                scrape_page = context.new_page()
                try:
                    logger.info(f"Playwright: Crawling candidate URL '{url}'...")
                    page_resp = scrape_page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                    scrape_page.wait_for_timeout(1200)

                    actual_url = scrape_page.url
                    page_title = scrape_page.title() or initial_title or url

                    # Clean boilerplate elements
                    raw_text = scrape_page.evaluate('''() => {
                        const removals = document.querySelectorAll(
                            'script, style, noscript, nav, footer, header, aside, .ad, .ads, .sidebar, #comments, .cookie-banner, .cookie-notice, .modal, .popup'
                        );
                        removals.forEach(el => el.remove());
                        return document.body ? document.body.innerText : '';
                    }''')

                    cleaned_text = cls._clean_scraped_text(raw_text)
                    words = len(cleaned_text.split())

                    if words >= 28 and not any(p['url'] == actual_url for p in pages_content):
                        pages_content.append({
                            'url': actual_url,
                            'title': page_title[:400],
                            'text': cleaned_text,
                            'words': words,
                        })
                        crawled_domains.add(domain)
                        logger.info(f"Playwright: Successfully crawled '{page_title}' ({words} words) from {actual_url}")
                except Exception as s_err:
                    # If navigation triggered a download because it was a PDF
                    if "Download is starting" in str(s_err) or ".pdf" in url.lower():
                        try:
                            import requests
                            import pymupdf
                            resp = requests.get(url, headers={'User-Agent': user_agent}, timeout=10)
                            if resp.status_code == 200 and resp.content:
                                doc = pymupdf.open(stream=resp.content, filetype='pdf')
                                pdf_text = "\n".join(pg.get_text() for pg in doc[:15])
                                cleaned_text = cls._clean_scraped_text(pdf_text)
                                words = len(cleaned_text.split())
                                if words >= 28 and not any(p['url'] == url for p in pages_content):
                                    pages_content.append({
                                        'url': url,
                                        'title': initial_title[:400],
                                        'text': cleaned_text,
                                        'words': words,
                                    })
                                    crawled_domains.add(domain)
                                    logger.info(f"Playwright: Recovered PDF download '{initial_title}' ({words} words)")
                        except Exception:
                            pass
                    else:
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
        text = re.sub(r'[\r\t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        lines = [line.strip() for line in text.split('\n') if len(line.strip()) > 3]
        return '\n\n'.join(lines)
