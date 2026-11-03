"""
arXiv API Connector.
https://arxiv.org/ - Open-access scientific repository for Physics, Mathematics, Computer Science, and AI.
"""
import logging
import urllib.parse
import xml.etree.ElementTree as ET
import requests
from typing import List
from datetime import datetime
from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class ArxivConnector(BaseSourceConnector):
    """Connector for arXiv open-access preprint archive API."""

    @property
    def id(self) -> str:
        return 'arxiv'

    @property
    def name(self) -> str:
        return 'arXiv'

    @property
    def source_type(self) -> str:
        return 'open_access'

    @property
    def description(self) -> str:
        return (
            "Open-access archive for 2.4+ million scholarly articles in computer science, "
            "mathematics, physics, quantitative biology, and electrical engineering."
        )

    def is_available(self) -> bool:
        return True

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 4:
            return []

        # Sanitize query for arXiv query parser
        clean_q = query_text.strip().replace('"', '').replace(':', '')[:150]
        encoded_query = urllib.parse.quote(clean_q)
        url = f"http://export.arxiv.org/api/query?search_query=all:{encoded_query}&start=0&max_results={min(max_results, 8)}"

        try:
            resp = requests.get(url, headers={'User-Agent': 'ProovexaArxivConnector/2.0'}, timeout=7)
            if resp.status_code != 200:
                logger.warning(f"arXiv API returned HTTP {resp.status_code}")
                return []

            root = ET.fromstring(resp.text)
            ns = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom',
            }

            results = []
            entries = root.findall('atom:entry', ns)

            for entry in entries:
                title_elem = entry.find('atom:title', ns)
                title = title_elem.text.strip().replace('\n', ' ') if title_elem is not None and title_elem.text else ''
                if not title:
                    continue

                summary_elem = entry.find('atom:summary', ns)
                summary = summary_elem.text.strip().replace('\n', ' ') if summary_elem is not None and summary_elem.text else ''

                # Authors
                author_elems = entry.findall('atom:author', ns)
                author_names = []
                for a in author_elems:
                    name_elem = a.find('atom:name', ns)
                    if name_elem is not None and name_elem.text:
                        author_names.append(name_elem.text.strip())
                author_str = ", ".join(author_names[:3])
                if len(author_names) > 3:
                    author_str += " et al."

                # Link
                id_elem = entry.find('atom:id', ns)
                item_url = id_elem.text.strip() if id_elem is not None and id_elem.text else ""

                # Date
                published_elem = entry.find('atom:published', ns)
                pub_date = None
                if published_elem is not None and published_elem.text:
                    try:
                        pub_date = datetime.strptime(published_elem.text[:10], '%Y-%m-%d').date()
                    except Exception:
                        pass

                # DOI if published in a peer-reviewed journal
                doi_elem = entry.find('arxiv:doi', ns)
                doi = doi_elem.text.strip() if doi_elem is not None and doi_elem.text else ""

                content_text = f"{title}. {summary}" if summary else title

                results.append(SourceProviderResult(
                    title=title,
                    author=author_str,
                    publication_date=pub_date,
                    url=item_url,
                    doi=doi,
                    text=content_text,
                    source_type='open_access',
                    provider_name='arXiv',
                    journal_or_publisher='arXiv.org Preprint Repository',
                    access_limitations='Open Access (arXiv Non-exclusive distribution license)',
                ))

            return results
        except Exception as e:
            logger.warning(f"arXiv search exception: {e}")
            return []

    def get_rate_limit_info(self) -> dict:
        return {
            'rate_limit': '1 request every 3 seconds per arXiv API guidelines',
            'terms_url': 'https://info.arxiv.org/help/api/tou.html',
            'license_info': 'arXiv Open Access Distribution License',
        }
