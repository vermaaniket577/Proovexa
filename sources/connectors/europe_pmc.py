"""
Europe PMC REST API Connector.
https://europepmc.org/ - Life sciences and biomedical literature database.
"""
import logging
import requests
from typing import List
from datetime import datetime
from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class EuropePMCConnector(BaseSourceConnector):
    """Connector for Europe PMC open-access biomedical literature API."""

    @property
    def id(self) -> str:
        return 'europe_pmc'

    @property
    def name(self) -> str:
        return 'Europe PMC'

    @property
    def source_type(self) -> str:
        return 'academic'

    @property
    def description(self) -> str:
        return (
            "Open science platform providing access to 44+ million life-sciences research publications, "
            "PubMed records, preprints, patents, and full-text PMC articles."
        )

    def is_available(self) -> bool:
        return True

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 4:
            return []

        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {
            'query': query_text.strip()[:200],
            'format': 'json',
            'resultType': 'core',
            'pageSize': min(max_results, 8),
        }

        try:
            resp = requests.get(url, params=params, headers={'User-Agent': 'ProovexaEuropePMC/2.0'}, timeout=7)
            if resp.status_code != 200:
                logger.warning(f"Europe PMC returned HTTP {resp.status_code}")
                return []

            data = resp.json()
            items = data.get('resultList', {}).get('result', [])
            results = []

            for item in items:
                title = item.get('title', '').strip()
                if not title:
                    continue

                author_str = item.get('authorString', '')
                doi = item.get('doi', '')
                pmcid = item.get('pmcid', '')
                abstract = item.get('abstractText', '') or ''

                item_url = ""
                if pmcid:
                    item_url = f"https://europepmc.org/article/PMC/{pmcid}"
                elif doi:
                    item_url = f"https://doi.org/{doi}"
                elif item.get('id'):
                    item_url = f"https://europepmc.org/article/MED/{item.get('id')}"

                # Date
                pub_date = None
                pub_year = item.get('pubYear')
                if pub_year:
                    try:
                        pub_date = datetime(int(pub_year), 1, 1).date()
                    except Exception:
                        pass

                journal = item.get('journalTitle', '') or item.get('journalInfo', {}).get('journal', {}).get('title', '')
                content_text = f"{title}. {abstract}" if abstract else title

                results.append(SourceProviderResult(
                    title=title,
                    author=author_str,
                    publication_date=pub_date,
                    url=item_url,
                    doi=doi,
                    text=content_text,
                    source_type='academic',
                    provider_name='Europe PMC',
                    journal_or_publisher=journal,
                    access_limitations='Europe PMC Open Access Subset',
                    raw_metadata=item,
                ))

            return results
        except Exception as e:
            logger.warning(f"Europe PMC search exception: {e}")
            return []

    def get_rate_limit_info(self) -> dict:
        return {
            'rate_limit': 'Up to 10 requests/second',
            'terms_url': 'https://europepmc.org/RestfulWebService',
            'license_info': 'Europe PMC Terms of Use (Open Access Subset)',
        }
