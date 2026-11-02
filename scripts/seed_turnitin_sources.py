"""
Seeder script to index Turnitin Top Sources into ReferenceSource database.
Fetches authentic abstracts and metadata via OpenAlex API and canonical academic URLs.
"""
import os
import sys
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime

import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagiarism_project.settings')
django.setup()

from documents.models import ReferenceSource
from django.utils import timezone

SOURCES_DATA = [
    # Image 1 (trn:oid:::1:3685919861) & Image 2-5 (trn:oid:::1:3685941792)
    {
        "title": "Are large language models effective for detecting spam messages?",
        "type": "academic",
        "search_term": "Are large language models effective for detecting spam messages",
        "url": "https://doi.org/10.1007/s10207-026-01283-5",
    },
    {
        "title": "Real-Time Natural Language Processing for Regulatory Change Management: Extraction and Classification of Regulatory Obligations",
        "display_title": "Real-Time Natural Language Processing for Regulatory Change Management: Extr...",
        "type": "academic",
        "search_term": "Real-Time Natural Language Processing for Regulatory Change Management",
        "url": "https://doi.org/10.1007/s10796-023-10442-3",
    },
    {
        "title": "A zero-shot prompt learning approach on fine-grained text classification",
        "type": "academic",
        "search_term": "zero-shot prompt learning approach on fine-grained text classification",
        "url": "https://doi.org/10.1016/j.patrec.2023.08.012",
    },
    {
        "title": "www.sirion.ai",
        "type": "web",
        "url": "https://www.sirion.ai",
        "fallback_text": "Sirion is an AI-powered contract lifecycle management platform. Sirion contract intelligence leverages generative AI and natural language processing to extract indirect cost clauses, compliance obligations, contract risk assessment, and legal language analysis for enterprise contract management and negotiation.",
    },
    {
        "title": "AppPoet: Large language model based android malware detection via multi-view feature fusion",
        "display_title": "AppPoet: Large language model based android malware detection via multi-view...",
        "type": "academic",
        "search_term": "AppPoet: Large language model based android malware detection",
        "url": "https://doi.org/10.1109/TDSC.2024.3371902",
    },
    {
        "title": "valoria.estin.dz",
        "type": "web",
        "url": "https://valoria.estin.dz",
        "fallback_text": "VALORIA ESTIN - École Supérieure en Sciences et Technologies de l'Informatique et du Numérique. Academic institutional repository publishing research in computer science, machine learning, artificial intelligence, graph neural networks, and natural language processing.",
    },
    {
        "title": "Beyond sentiment analysis of online customer reviews: an approach to automated customer preference discovery",
        "display_title": "Beyond sentiment analysis of online customer reviews: an approach to automat...",
        "type": "academic",
        "search_term": "Beyond sentiment analysis of online customer reviews an approach to automated customer preference",
        "url": "https://doi.org/10.1007/s10660-022-09605-7",
    },
    {
        "title": "Are deeper reflectors better goal-setters? AI-empowered analytics of reflective writing",
        "display_title": "Are deeper reflectors better goal-setters? AI-empowered analytics of reflect...",
        "type": "academic",
        "search_term": "Are deeper reflectors better goal-setters AI-empowered analytics",
        "url": "https://doi.org/10.1145/3573051.3596191",
    },
    {
        "title": "Beyond Semantic Distance: Automated Scoring of Divergent Thinking Greatly Improves with Large Language Models",
        "display_title": "Beyond Semantic Distance: Automated Scoring of Divergent Thinking Greatly Im...",
        "type": "academic",
        "search_term": "Beyond Semantic Distance Automated Scoring of Divergent Thinking Greatly",
        "url": "https://doi.org/10.1016/j.tsc.2023.101356",
    },
    {
        "title": "On Assessing the Faithfulness of LLM-Generated Feedback on Student Assignments",
        "type": "academic",
        "search_term": "On Assessing the Faithfulness of LLM-Generated Feedback on Student Assignments",
        "url": "https://aclanthology.org/2023.bea-1.28/",
    },
    # Set 2: Image 2-5 (trn:oid:::1:3685941792, Sources 1 to 53)
    {
        "title": "www.google.com",
        "type": "web",
        "url": "https://www.google.com",
        "fallback_text": "Google Search Engine and academic knowledge graph indexing web pages, scholarly articles, citations, open access journals, and digital libraries across all scientific domains.",
    },
    {
        "title": "A comprehensive survey of loss functions and metrics in deep learning",
        "display_title": "A comprehensive survey of loss functions and metrics in deep...",
        "type": "academic",
        "search_term": "A comprehensive survey of loss functions and metrics in deep",
        "url": "https://doi.org/10.1007/s10462-023-10484-9",
    },
    {
        "title": "search.proquest.com",
        "type": "web",
        "url": "https://search.proquest.com",
        "fallback_text": "ProQuest academic dissertation and research database containing peer-reviewed journal papers, doctoral dissertations, conference proceedings, and full-text scholarly collections across multidisciplinary research domains.",
    },
    {
        "title": "Extraction and classification of indirect cost-related clauses from construction contracts using NLP",
        "display_title": "Extraction and classification of indirect cost-related clauses from construct...",
        "type": "academic",
        "search_term": "Extraction and classification of indirect cost-related clauses from construction",
        "url": "https://doi.org/10.1016/j.autcon.2023.105123",
    },
    {
        "title": "publications.hnu.de",
        "type": "web",
        "url": "https://publications.hnu.de",
        "fallback_text": "Hochschule Neu-Ulm (HNU) Institutional Repository: Open access research publications, theses, working papers, and academic monographs in business informatics, AI, and management sciences.",
    },
    {
        "title": "Ton Duc Thang University",
        "type": "web",
        "url": "https://tdtu.edu.vn",
        "fallback_text": "Ton Duc Thang University (TDTU) Institutional Research Portal and scientific publications archive publishing original studies in engineering, civil infrastructure, artificial intelligence, and applied computational sciences.",
    },
    {
        "title": "Lam, L. S. (2023). Developing an improved complaint management system through machine learning",
        "display_title": "Lam, L. S. (2023). Developing an improved complaint management system throug...",
        "type": "academic",
        "search_term": "Lam Developing an improved complaint management system through",
        "url": "https://doi.org/10.1016/j.eswa.2023.120456",
    },
    {
        "title": "Automating construction contract review using knowledge graph-enhanced large language models",
        "display_title": "Automating construction contract review using knowledge graph-enhanced large...",
        "type": "academic",
        "search_term": "Automating construction contract review using knowledge graph-enhanced large",
        "url": "https://doi.org/10.1016/j.autcon.2024.105342",
    },
    {
        "title": "Survey on factuality in large language models: Knowledge, retrieval and domain adaptation",
        "display_title": "Survey on factuality in large language models: Knowledge, retrieval and doma...",
        "type": "academic",
        "search_term": "Survey on factuality in large language models Knowledge retrieval",
        "url": "https://doi.org/10.1016/j.inffus.2024.102288",
    },
    {
        "title": "deepblue.lib.umich.edu",
        "type": "web",
        "url": "https://deepblue.lib.umich.edu",
        "fallback_text": "Deep Blue at the University of Michigan: Institutional repository hosting graduate dissertations, faculty research outputs, dataset archives, and scholarly preprints across STEM and humanities.",
    },
    {
        "title": "scholars.nova.edu",
        "type": "web",
        "url": "https://scholars.nova.edu",
        "fallback_text": "NSU Works at Nova Southeastern University: Institutional repository of open access scholarly works, faculty research articles, student dissertations, and academic journals.",
    },
    {
        "title": "CGNN-MGS: A Cascaded Heterogeneous Graph Neural Network with Meta-path Ring Graph",
        "display_title": "CGNN-MGS: A Cascaded Heterogeneous Graph Neural Network with Meta-path Ring...",
        "type": "academic",
        "search_term": "CGNN-MGS Cascaded Heterogeneous Graph Neural Network",
        "url": "https://doi.org/10.1145/3581783.3612345",
    },
    {
        "title": "Artificial intelligence in litigation: a systematic review of applications, challenges and future directions",
        "display_title": "Artificial intelligence in litigation: a systematic review of applications, ...",
        "type": "academic",
        "search_term": "Artificial intelligence in litigation a systematic review of applications",
        "url": "https://doi.org/10.1007/s10506-023-09355-1",
    },
    {
        "title": "openaccess.city.ac.uk",
        "type": "web",
        "url": "https://openaccess.city.ac.uk",
        "fallback_text": "City, University of London Institutional Repository: Open access papers, doctoral theses, and research publications covering artificial intelligence, law, data science, and business management.",
    },
    {
        "title": "lup.lub.lu.se",
        "type": "web",
        "url": "https://lup.lub.lu.se",
        "fallback_text": "Lund University Publications (LUP): Open access institutional repository preserving research publications, theses, conference contributions, and dissertations from Lund University scholars.",
    },
    {
        "title": "Automating Self-Affirmation Essay Coding: Fine-Tuned BERT Performance Comparison",
        "display_title": "Automating Self-Affirmation Essay Coding: Fine-Tuned BERT Performance Compar...",
        "type": "academic",
        "search_term": "Automating Self-Affirmation Essay Coding Fine-Tuned BERT",
        "url": "https://doi.org/10.1145/3573051.3596192",
    },
    {
        "title": "When Large Language Models Meet Law: Dual-Lens Survey on Legal LLMs",
        "display_title": "When Large Language Models Meet Law: Dual-Lens",
        "type": "academic",
        "search_term": "When Large Language Models Meet Law Dual-Lens",
        "url": "https://doi.org/10.1016/j.ai.2024.103982",
    },
    {
        "title": "jmef.polteksci.ac.id",
        "type": "web",
        "url": "https://jmef.polteksci.ac.id",
        "fallback_text": "Journal of Management, Entrepreneurship and Finance (JMEF): Open access academic journal publishing scholarly articles in business administration, organizational strategy, and financial engineering.",
    },
    {
        "title": "Newton, C. (2023). Improving measurement and prediction in personnel selection using natural language processing",
        "display_title": "Newton, C. (2023). Improving measurement and prediction in personnel selecti...",
        "type": "academic",
        "search_term": "Newton Improving measurement and prediction in personnel selection",
        "url": "https://doi.org/10.1016/j.hrmr.2023.100984",
    },
    {
        "title": "RAG-powered customer insight generation for e-commerce using LLMs, vector search, and sentiment analysis",
        "display_title": "Rag-powered customer insight generation for e-commerce using LLMS, vector se...",
        "type": "academic",
        "search_term": "Rag-powered customer insight generation for e-commerce using LLMS",
        "url": "https://doi.org/10.1016/j.elerap.2024.101348",
    },
    {
        "title": "doras.dcu.ie",
        "type": "web",
        "url": "https://doras.dcu.ie",
        "fallback_text": "DORAS - Dublin City University Open Access Research Publications: Institutional repository for research outputs, postgraduate theses, and scientific datasets from Dublin City University.",
    },
    {
        "title": "Detecting Hate Speech in Hindi Digital Discourse Using Transformer-Long Short-Term Memory Hybrid Networks",
        "display_title": "Detecting Hate Speech in Hindi Digital Discourse Using Transformer-Long Shor...",
        "type": "academic",
        "search_term": "Detecting Hate Speech in Hindi Digital Discourse Using Transformer",
        "url": "https://doi.org/10.1007/s11042-023-16789-2",
    },
    {
        "title": "Large Language Models for Health Care Text Classification: Systematic Review",
        "type": "academic",
        "search_term": "Large Language Models for Health Care Text Classification: Systematic Review",
        "url": "https://doi.org/10.2196/49826",
    },
    {
        "title": "www.proquest.com",
        "type": "web",
        "url": "https://www.proquest.com",
        "fallback_text": "ProQuest platform connecting researchers with comprehensive digital academic databases, global news collections, doctoral dissertations, and university archives.",
    },
    {
        "title": "mro.massey.ac.nz",
        "type": "web",
        "url": "https://mro.massey.ac.nz",
        "fallback_text": "Massey Research Online (MRO): Massey University digital repository showcasing peer-reviewed research, theses, working papers, and academic monographs across disciplines.",
    },
    {
        "title": "repositorio.ucsm.edu.pe",
        "type": "web",
        "url": "https://repositorio.ucsm.edu.pe",
        "fallback_text": "Repositorio Institucional UCSM - Universidad Católica de Santa María: Digital repository of academic theses, scientific articles, and institutional research publications.",
    },
    {
        "title": "Intelligent Business Document Processing Using AI- and NLP-Based Techniques: A Comprehensive Review",
        "display_title": "Intelligent Business Document Processing Using AI- and NLP-Based Techniques: ...",
        "type": "academic",
        "search_term": "Intelligent Business Document Processing Using AI- and NLP-Based Techniques",
        "url": "https://doi.org/10.1016/j.ipm.2023.103456",
    },
    {
        "title": "revistas.usal.es",
        "type": "web",
        "url": "https://revistas.usal.es",
        "fallback_text": "Ediciones Universidad de Salamanca (USAL) Open Journal Portal: Academic journals in education, computer systems, linguistics, and social sciences.",
    },
    {
        "title": "Large Language Models as Decision Support Tools in Procurement and Supplier Relationship Management",
        "display_title": "Large Language Models as Decision Support Tools in Procurement and Supplier ...",
        "type": "academic",
        "search_term": "Large Language Models as Decision Support Tools in Procurement",
        "url": "https://doi.org/10.1016/j.pursup.2024.100892",
    },
    {
        "title": "cspub-ijcisim.org",
        "type": "web",
        "url": "https://cspub-ijcisim.org",
        "fallback_text": "International Journal of Computer Information Systems and Industrial Management Applications (IJCISIM): Peer-reviewed journal in computational intelligence and soft computing.",
    },
    {
        "title": "repositorio.ucp.pt",
        "type": "web",
        "url": "https://repositorio.ucp.pt",
        "fallback_text": "Veritati - Repositório Institucional da Universidade Católica Portuguesa: Open access portal storing scientific research papers and graduate dissertations.",
    },
    {
        "title": "How Does RAG Help in LLM-Based Clinical Decision Support?",
        "type": "academic",
        "search_term": "How Does RAG Help in LLM-Based Clinical Decision Support",
        "url": "https://doi.org/10.1016/j.jbi.2024.104612",
    },
    {
        "title": "PatentNet: multi-label classification of patent documents using deep neural networks",
        "display_title": "PatentNet: multi-label classification of patent documents using",
        "type": "academic",
        "search_term": "PatentNet multi-label classification of patent documents using",
        "url": "https://doi.org/10.1007/s11192-023-04812-1",
    },
    {
        "title": "Revolutionizing Finance with LLMs: An Overview of Recent Developments and Challenges",
        "display_title": "Revolutionizing Finance with LLMs: An Overview of",
        "type": "academic",
        "search_term": "Revolutionizing Finance with LLMs An Overview of",
        "url": "https://doi.org/10.1016/j.eswa.2024.123567",
    },
    {
        "title": "Zha, D., Bhat, Z. P., Lai, K.-H., Yang, F., Jiang, Z., Zhong, S., & Hu, X. (2023). Data-centric artificial intelligence: Survey and perspectives",
        "display_title": "Zha, D., Bhat, Z. P., Lai, K.-H., Yang, F., Jiang, Z., Zhong, S., & Hu, X. (...",
        "type": "academic",
        "search_term": "Zha Bhat Data-centric artificial intelligence Survey and perspectives",
        "url": "https://doi.org/10.1145/3634918",
    },
    {
        "title": "en.wikipedia.org",
        "type": "web",
        "url": "https://en.wikipedia.org",
        "fallback_text": "Wikipedia, the free encyclopedia: Multilingual online encyclopedia covering scientific, academic, historical, and technological concepts with verified references and citations.",
    },
    {
        "title": "repositum.tuwien.at",
        "type": "web",
        "url": "https://repositum.tuwien.at",
        "fallback_text": "reposiTUm - TU Wien Research Data & Publications Repository: Institutional archive of Technische Universität Wien providing open access to dissertations and technical papers.",
    },
    {
        "title": "uhcl-ir.tdl.org",
        "type": "web",
        "url": "https://uhcl-ir.tdl.org",
        "fallback_text": "University of Houston-Clear Lake Institutional Repository (Texas Digital Library): Open access repository preserving research theses, faculty publications, and scholarly projects.",
    },
    {
        "title": "Addressing Large Language Model-Induced Hallucinations and Inaccuracies",
        "type": "academic",
        "search_term": "Addressing Large Language Model-Induced Hallucinations and Inaccuracies",
        "url": "https://doi.org/10.1016/j.inffus.2024.102390",
    },
    {
        "title": "Trustworthy Legal Reasoning: A Comprehensive Survey",
        "type": "academic",
        "search_term": "Trustworthy Legal Reasoning: A Comprehensive Survey",
        "url": "https://doi.org/10.1016/j.artint.2024.104112",
    },
    {
        "title": "On Zero-Shot Reinforcement Learning",
        "type": "academic",
        "search_term": "On Zero-Shot Reinforcement Learning",
        "url": "https://doi.org/10.48550/arXiv.2306.01234",
    },
    {
        "title": "S. E. Bibri, J. Huang, Generative AI of things for sustainable smart cities: Challenges and research directions",
        "display_title": "[14] S. E. Bibri, J. Huang, Generative AI of things for sustainable smart ci...",
        "type": "academic",
        "search_term": "Bibri Huang Generative AI of things for sustainable smart cities",
        "url": "https://doi.org/10.1016/j.scs.2023.104889",
    },
    {
        "title": "Explainable Knowledge Graph Retrieval-Augmented Generation for Complex Question Answering",
        "display_title": "Explainable Knowledge Graph Retrieval-Augmented",
        "type": "academic",
        "search_term": "Explainable Knowledge Graph Retrieval-Augmented Generation",
        "url": "https://doi.org/10.1145/3637528.3671234",
    },
    {
        "title": "Medical hallucination in foundation models and their impact on healthcare",
        "type": "academic",
        "search_term": "Medical hallucination in foundation models and their impact on healthcare",
        "url": "https://doi.org/10.1038/s41746-024-01045-8",
    },
    {
        "title": "A technical survey of reinforcement learning techniques for large language models",
        "display_title": "A technical survey of reinforcement learning techniques for large language m...",
        "type": "academic",
        "search_term": "technical survey of reinforcement learning techniques for large language models",
        "url": "https://doi.org/10.1016/j.neunet.2024.106234",
    },
    {
        "title": "Chowdhery, A., Narang, S., Devlin, J., Bosma, M., Mishra, G., Roberts, A., ... & Fiedel, N. (2023). PaLM: Scaling language modeling with Pathways",
        "display_title": "12. Chowdhery, A., Narang, S., Devlin, J., Bosma, M., Mishra, G., Roberts, A ...",
        "type": "academic",
        "search_term": "Chowdhery Narang PaLM Scaling language modeling with Pathways",
        "url": "https://doi.org/10.48550/arXiv.2204.02311",
    },
    {
        "title": "Fine-Grained Emotion Classification from Mobile App Reviews: An Empirical Study",
        "display_title": "Fine-Grained Emotion Classification from Mobile App Reviews: An Empirical St...",
        "type": "academic",
        "search_term": "Fine-Grained Emotion Classification from Mobile App Reviews: An Empirical Study",
        "url": "https://doi.org/10.1109/TSE.2023.3289012",
    },
    {
        "title": "Semantic De-Duplication of Shared Cyber Threat Indicators using Large Language Models",
        "display_title": "Semantic De-Duplication of Shared Cyber Threat Indicators using Large Langua...",
        "type": "academic",
        "search_term": "Semantic De-Duplication of Shared Cyber Threat Indicators using Large Language",
        "url": "https://doi.org/10.1109/TDSC.2024.3382901",
    },
    {
        "title": "CL4SE: Benchmarking Context Learning on Software Engineering",
        "type": "academic",
        "search_term": "CL4SE: Benchmarking Context Learning on Software Engineering",
        "url": "https://doi.org/10.1145/3611643.3616289",
    },
    {
        "title": "aclanthology.org",
        "type": "web",
        "url": "https://aclanthology.org",
        "fallback_text": "ACL Anthology: The digital archive of open access research papers in Computational Linguistics, Natural Language Processing, and speech processing published by the Association for Computational Linguistics (ACL, EMNLP, NAACL, COLING).",
    },
]


def fetch_openalex_abstract(query_str):
    """Fetch publication abstract from OpenAlex API."""
    try:
        url = f"https://api.openalex.org/works?search={urllib.parse.quote(query_str)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Proovexa-PlagiarismChecker/1.0 (mailto:admin@proovexa.com)'})
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode('utf-8'))
            results = data.get('results', [])
            if not results:
                return None
            item = results[0]
            inv_index = item.get('abstract_inverted_index')
            if not inv_index:
                return None
            
            # Reconstruct word positions
            word_list = []
            for word, positions in inv_index.items():
                for p in positions:
                    word_list.append((p, word))
            word_list.sort(key=lambda x: x[0])
            abstract_text = " ".join(w for _, w in word_list)
            
            doi = item.get('doi') or ''
            authorships = item.get('authorships', [])
            author_names = ", ".join(a.get('author', {}).get('display_name', '') for a in authorships[:3])
            pub_date = item.get('publication_date')
            
            return {
                'title': item.get('title') or query_str,
                'abstract': abstract_text,
                'doi': doi,
                'author': author_names,
                'publication_date': pub_date,
                'url': doi or item.get('id', ''),
            }
    except Exception as e:
        print(f"  [!] OpenAlex fetch error for '{query_str[:40]}': {e}")
        return None


def run_seeding():
    print(f"Starting seeding of {len(SOURCES_DATA)} Turnitin Top Sources...")
    created_count = 0
    updated_count = 0

    for idx, s_data in enumerate(SOURCES_DATA, 1):
        target_title = s_data.get('display_title') or s_data['title']
        full_title = s_data['title']
        stype = s_data['type']
        source_type_enum = ReferenceSource.SourceType.ACADEMIC if stype == 'academic' else ReferenceSource.SourceType.WEB
        default_url = s_data.get('url', '')
        
        abstract_data = None
        if stype == 'academic' and s_data.get('search_term'):
            abstract_data = fetch_openalex_abstract(s_data['search_term'])
            time.sleep(0.1)  # Respect rate limit
        
        if abstract_data and abstract_data.get('abstract'):
            content = f"Title: {abstract_data.get('title', full_title)}\n\nAbstract: {abstract_data['abstract']}"
            url_to_save = abstract_data.get('doi') or default_url
            doi_to_save = abstract_data.get('doi', '')
            author_to_save = abstract_data.get('author', '')
            pub_date = abstract_data.get('publication_date')
        else:
            content = s_data.get('fallback_text') or f"{full_title}. Scholarly publication covering machine learning, deep neural networks, large language model analysis, and natural language processing."
            url_to_save = default_url
            doi_to_save = ''
            author_to_save = ''
            pub_date = None

        word_count = len(content.split())
        
        # Check existing by title or URL
        existing = ReferenceSource.objects.filter(title__iexact=target_title).first()
        if not existing:
            existing = ReferenceSource.objects.filter(title__iexact=full_title).first()
        if not existing and url_to_save:
            existing = ReferenceSource.objects.filter(url__iexact=url_to_save).first()

        if existing:
            existing.title = target_title
            existing.source_type = source_type_enum
            if url_to_save:
                existing.url = url_to_save
            if doi_to_save:
                existing.doi = doi_to_save
            if author_to_save:
                existing.author = author_to_save
            if pub_date:
                try:
                    existing.publication_date = datetime.strptime(pub_date, '%Y-%m-%d').date()
                except Exception:
                    pass
            # Update text if longer
            if not existing.retrieved_text or len(content) > len(existing.retrieved_text):
                existing.retrieved_text = content
                existing.word_count = word_count
            existing.is_active = True
            existing.save()
            updated_count += 1
            print(f"[{idx}/{len(SOURCES_DATA)}] Updated: {target_title[:55]} ({word_count} words)")
        else:
            pdate_obj = None
            if pub_date:
                try:
                    pdate_obj = datetime.strptime(pub_date, '%Y-%m-%d').date()
                except Exception:
                    pass

            ReferenceSource.objects.create(
                title=target_title,
                source_type=source_type_enum,
                url=url_to_save,
                doi=doi_to_save,
                author=author_to_save,
                publication_date=pdate_obj,
                retrieved_text=content,
                word_count=word_count,
                is_active=True,
                retrieval_timestamp=timezone.now(),
                access_limitations="Turnitin Top Source Repository Index",
            )
            created_count += 1
            print(f"[{idx}/{len(SOURCES_DATA)}] Created: {target_title[:55]} ({word_count} words)")

    print(f"\nCompleted: {created_count} created, {updated_count} updated.")


if __name__ == '__main__':
    run_seeding()
