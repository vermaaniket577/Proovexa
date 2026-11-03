"""
PubMed Central (PMC) NCBI E-Utilities API Connector.
https://pmc.ncbi.nlm.nih.gov/ - National Center for Biotechnology Information (NCBI) biomedical archive.
"""
import logging
import requests
from typing import List
from datetime import datetime
from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class PubMedCentralConnector(BaseSourceConnector):
    """Connector for NCBI PubMed Central (PMC) repository via E-Utilities."""

    @property
    def id(self) -> str:
        return 'pmc'

    @property
    def name(self) -> str:
        return 'PubMed Central'

    @property
    def source_type(self) -> str:
        return 'academic'

    @property
    def description(self) -> str:
        return (
            "National Institutes of Health (NIH) free digital archive of 9+ million biomedical and "
            "life sciences journal articles."
        )

    def is_available(self) -> bool:
        return True

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        if not query_text or len(query_text.strip()) < 4:
            return []

        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

        try:
            # Step 1: Query PMC IDs
            s_params = {
                'db': 'pmc',
                'term': query_text.strip()[:180],
                'retmode': 'json',
                'retmax': min(max_results, 6),
                'tool': 'ProovexaChecker',
                'email': 'admin@proovexa.edu',
            }
            s_resp = requests.get(search_url, params=s_params, timeout=7)
            if s_resp.status_code != 200:
                return []

            id_list = s_resp.json().get('esearchresult', {}).get('idlist', [])
            if not id_list:
                return []

            # Step 2: Fetch article summaries
            sum_params = {
                'db': 'pmc',
                'id': ",".join(id_list),
                'retmode': 'json',
                'tool': 'ProovexaChecker',
                'email': 'admin@proovexa.edu',
            }
            sum_resp = requests.get(summary_url, params=sum_params, timeout=7)
            if sum_resp.status_code != 200:
                return []

            sum_data = sum_resp.json().get('result', {})
            results = []

            for uid in id_list:
                doc = sum_data.get(str(uid), {})
                title = doc.get('title', '').strip()
                if not title:
                    continue

                # Authors
                authors = [a.get('name', '') for a in doc.get('authors', []) if a.get('name')]
                author_str = ", ".join(authors[:3])
                if len(authors) > 3:
                    author_str += " et al."

                # Publication date
                pub_date = None
                pubdate_str = doc.get('pubdate') or doc.get('epubdate')
                if pubdate_str:
                    try:
                        pub_date = datetime.strptime(pubdate_str[:10], '%Y %b %d').date()
                    except Exception:
                        try:
                            pub_date = datetime.strptime(pubdate_str[:4], '%Y').date()
                        except Exception:
                            pass

                article_ids = doc.get('articleids', [])
                doi = ""
                pmcid = ""
                for aid in article_ids:
                    if aid.get('idtype') == 'doi':
                        doi = aid.get('value', '')
                    elif aid.get('idtype') == 'pmcid':
                        pmcid = aid.get('value', '')

                item_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{uid}/"
                journal = doc.get('source', '') or doc.get('fulljournalname', '')

                results.append(SourceProviderResult(
                    title=title,
                    author=author_str,
                    publication_date=pub_date,
                    url=item_url,
                    doi=doi,
                    text=f"{title}. Published in {journal}.",
                    source_type='academic',
                    provider_name='PubMed Central',
                    journal_or_publisher=journal,
                    access_limitations='NCBI PubMed Central Open Access Subset',
                    raw_metadata=doc,
                ))

            return results
        except Exception as e:
            logger.warning(f"PubMed Central search exception: {e}")
            return []

    def get_rate_limit_info(self) -> dict:
        return {
            'rate_limit': '3 requests/second without NCBI API key; 10 req/s with key',
            'terms_url': 'https://www.ncbi.nlm.nih.gov/home/about/policies/',
            'license_info': 'NIH/NLM Open Access Policy & Terms',
        }
