"""
Registry and parallel dispatcher for all academic and web similarity connectors.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

from .base import BaseSourceConnector, SourceProviderResult
from .crossref import CrossrefConnector
from .crossref_preprints import CrossrefPreprintsConnector
from .openalex import OpenAlexConnector
from .arxiv import ArxivConnector
from .europe_pmc import EuropePMCConnector
from .pubmed_central import PubMedCentralConnector
from .doaj import DOAJConnector
from .semantic_scholar import SemanticScholarConnector
from .core import COREConnector
from .unpaywall import UnpaywallConnector
from .eric import ERICConnector
from .zenodo import ZenodoConnector
from .hal import HALOpenScienceConnector
from .base_search import BASEConnector
from .internet_archive import InternetArchiveConnector
from .common_crawl import CommonCrawlConnector
from .wikipedia import WikipediaConnector
from .web_search import WebSearchConnector
from .submitted_works import SubmittedWorksConnector
from .local_documents import LocalDocumentConnector
from .code_similarity import CodeSimilarityConnector
from .publishers import get_all_publisher_connectors

logger = logging.getLogger(__name__)

# Registered connector singleton instances
_ALL_CONNECTORS: List[BaseSourceConnector] = [
    # Top Academic & Open Access Repositories
    CrossrefConnector(),
    CrossrefPreprintsConnector(),
    OpenAlexConnector(),
    COREConnector(),
    SemanticScholarConnector(),
    PubMedCentralConnector(),
    EuropePMCConnector(),
    DOAJConnector(),
    ArxivConnector(),
    UnpaywallConnector(),
    ERICConnector(),
    ZenodoConnector(),
    HALOpenScienceConnector(),
    BASEConnector(),
    # Internet & Web Archives
    InternetArchiveConnector(),
    CommonCrawlConnector(),
    WikipediaConnector(),
    WebSearchConnector(),
    # Submitted Works & Institutional Repositories
    SubmittedWorksConnector(),
    LocalDocumentConnector(),
    CodeSimilarityConnector(),
] + get_all_publisher_connectors()


def get_all_connectors() -> List[BaseSourceConnector]:
    """Returns list of all registered source connectors."""
    return _ALL_CONNECTORS


def get_available_connectors() -> List[BaseSourceConnector]:
    """Returns list of active/configured source connectors."""
    return [c for c in _ALL_CONNECTORS if c.is_available()]


def get_connector(connector_id: str) -> Optional[BaseSourceConnector]:
    """Finds a connector by its slug ID."""
    for c in _ALL_CONNECTORS:
        if c.id == connector_id:
            return c
    return None


def multi_source_search(
    queries: List[str],
    max_results_per_source: int = 3,
    connectors: Optional[List[BaseSourceConnector]] = None,
    timeout_seconds: float = 15.0,
) -> Dict[str, Any]:
    """
    Executes parallel search across all available academic and web source connectors.
    
    Args:
        queries: Distinctive phrases, sentences, or titles extracted from document
        max_results_per_source: Number of records per query per connector
        connectors: Optional explicit list of connectors to query
        timeout_seconds: Maximum wall time for network calls
        
    Returns:
        Dict with:
          'results': List of deduplicated SourceProviderResult objects
          'sources_checked': List of connector names that ran successfully
          'failed_sources': List of connector names that encountered errors/timeouts
          'total_retrieved': Total distinct results count
    """
    active_connectors = connectors or get_available_connectors()
    if not active_connectors or not queries:
        return {
            'results': [],
            'sources_checked': [],
            'failed_sources': [],
            'total_retrieved': 0,
        }

    # Dedup and limit queries for comprehensive multi-section coverage (up to 6 distinctive phrases)
    clean_queries = []
    seen_q = set()
    for q in queries:
        cq = q.strip()
        if len(cq) >= 5 and cq.lower() not in seen_q:
            clean_queries.append(cq)
            seen_q.add(cq.lower())
        if len(clean_queries) >= 6:
            break

    if not clean_queries:
        return {
            'results': [],
            'sources_checked': [],
            'failed_sources': [],
            'total_retrieved': 0,
        }

    harvested_results: List[SourceProviderResult] = []
    sources_checked = set()
    failed_sources = set()
    seen_urls = set()
    seen_titles = set()

    def _query_connector(conn: BaseSourceConnector, q: str):
        try:
            res = conn.search(q, max_results=max_results_per_source)
            return conn.id, conn.name, res, True
        except Exception as conn_err:
            logger.debug(f"Connector {conn.name} query failed: {conn_err}")
            return conn.id, conn.name, [], False

    tasks = []
    # Prioritize top academic and encyclopedic sources in worker queue
    # Send up to 2 most salient queries per connector with controlled threadpool to prevent external 429 rate limiting
    with ThreadPoolExecutor(max_workers=10) as executor:
        for conn in active_connectors:
            # Query top 2 distinctive phrases per provider
            for q in clean_queries[:2]:
                tasks.append(executor.submit(_query_connector, conn, q))

        try:
            for future in as_completed(tasks, timeout=timeout_seconds):
                try:
                    conn_id, conn_name, res_list, ok = future.result()
                    if ok:
                        sources_checked.add(conn_name)
                    else:
                        failed_sources.add(conn_name)
                    for item in res_list:
                        # Deduplication key by URL or DOI or normalized Title
                        norm_title = "".join(c for c in item.title.lower() if c.isalnum())
                        key_url = item.url or (f"doi:{item.doi}" if item.doi else norm_title)
                        if key_url and key_url in seen_urls:
                            continue
                        if norm_title and norm_title in seen_titles:
                            continue

                        if key_url:
                            seen_urls.add(key_url)
                        if norm_title:
                            seen_titles.add(norm_title)

                        harvested_results.append(item)
                except Exception as e:
                    logger.debug(f"Connector task exception: {e}")
        except TimeoutError:
            logger.info(f"Multi-source search reached timeout ({timeout_seconds}s); continuing with completed results.")

    # Only mark connectors as failed if they had no completed queries at all
    for conn in active_connectors:
        if conn.name not in sources_checked:
            failed_sources.add(conn.name)
        elif conn.name in failed_sources:
            failed_sources.remove(conn.name)

    return {
        'results': harvested_results,
        'sources_checked': sorted(list(sources_checked)),
        'failed_sources': sorted(list(failed_sources)),
        'total_retrieved': len(harvested_results),
    }
