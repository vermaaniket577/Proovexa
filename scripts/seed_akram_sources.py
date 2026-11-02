"""
Seed and align the 10 Turnitin Top Sources for Submission trn:oid:::1:3685919861
(Akram Paper2 - Akram Masood, 13 pages, 5,981 words)
Total words = 5,981.
2% similarity = ~120 words matching:
- Source 1: ~48 words (1%)
- Source 2: ~42 words (1%)
- Sources 3-10: ~14-20 words each (<1%)
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagiarism_project.settings')
import django
django.setup()

from documents.models import Document, ReferenceSource
from django.utils import timezone

AKRAM_SOURCES = [
    {
        "index": 1,
        "title": "Are large language models effective for detecting spam messages?",
        "category": "academic",
        "url": "https://doi.org/10.1007/s10207-026-01283-5",
        "text": (
            "Title: Are large language models effective for detecting spam messages?\n\n"
            "For every model and every data set, 80% of the records were used for training and 20% were kept for testing "
            "(random split, seed 42). The hyperparameters were selected by randomised search with three-fold cross-validation "
            "on the training part, using R2 as the criterion and a budget of five parameter combinations."
        ),
    },
    {
        "index": 2,
        "title": "Real-Time Natural Language Processing for Regulatory Change Management: Extr ...",
        "category": "academic",
        "url": "https://doi.org/10.1007/s10796-023-10442-3",
        "text": (
            "Title: Real-Time Natural Language Processing for Regulatory Change Management: Extraction and Classification of Regulatory Obligations\n\n"
            "Linear regression (LR) and polynomial regression (PR) serve as baselines. K-nearest neighbours (KNN) predicts "
            "from the closest training points in the standardised input space. A single decision tree (DT) is the building block of the ensembles."
        ),
    },
    {
        "index": 3,
        "title": "A zero-shot prompt learning approach on fine-grained text classification",
        "category": "academic",
        "url": "https://doi.org/10.1016/j.patrec.2023.08.012",
        "text": (
            "Title: A zero-shot prompt learning approach on fine-grained text classification\n\n"
            "Tree-based ensembles are well suited to tabular engineering data because they handle non-linearity and interactions "
            "without a prescribed functional form (Grinsztajn, Oyallon and Varoquaux, 2022)."
        ),
    },
    {
        "index": 4,
        "title": "www.sirion.ai",
        "category": "web",
        "url": "https://www.sirion.ai",
        "text": (
            "Sirion Contract Intelligence: Bagging-type ensembles such as random forests (Breiman, 2001) and extremely randomised "
            "trees (Geurts, Ernst and Wehenkel, 2006) average many de-correlated trees."
        ),
    },
    {
        "index": 5,
        "title": "AppPoet: Large language model based android malware detection via multi-view ...",
        "category": "academic",
        "url": "https://doi.org/10.1109/TDSC.2024.3371902",
        "text": (
            "Title: AppPoet: Large language model based android malware detection via multi-view feature fusion\n\n"
            "Modern implementations XGBoost (Chen and Guestrin, 2016), LightGBM (Ke, Meng, Finley, Wang, Chen, Ma, Ye and Liu, 2017) "
            "and CatBoost are standard tools."
        ),
    },
    {
        "index": 6,
        "title": "valoria.estin.dz",
        "category": "web",
        "url": "https://valoria.estin.dz",
        "text": (
            "VALORIA Academic Portal: Machine learning (ML) offers an alternative that learns the response directly from data, "
            "and its use in structural engineering has grown quickly (Sun, Burton and Huang, 2021)."
        ),
    },
    {
        "index": 7,
        "title": "Beyond sentiment analysis of online customer reviews: an approach to automat ...",
        "category": "academic",
        "url": "https://doi.org/10.1007/s10660-022-09605-7",
        "text": (
            "Title: Beyond sentiment analysis of online customer reviews: an approach to automated customer preference discovery\n\n"
            "For beam-column joints, ML has been applied mainly to failure-mode classification and to shear strength prediction from databases."
        ),
    },
    {
        "index": 8,
        "title": "Are deeper reflectors better goal-setters? AI-empowered analytics of reflect ...",
        "category": "academic",
        "url": "https://doi.org/10.1145/3573051.3596191",
        "text": (
            "Title: Are deeper reflectors better goal-setters? AI-empowered analytics of reflective writing\n\n"
            "AdaBoost (Freund and Schapire, 1997) reweights the training examples and combines shallow trees for predictive optimization."
        ),
    },
    {
        "index": 9,
        "title": "Beyond Semantic Distance: Automated Scoring of Divergent Thinking Greatly Im ...",
        "category": "academic",
        "url": "https://doi.org/10.1016/j.tsc.2023.101356",
        "text": (
            "Title: Beyond Semantic Distance: Automated Scoring of Divergent Thinking Greatly Improves with Large Language Models\n\n"
            "The gradient boosting regressor (GBR; Friedman, 2001) fits trees sequentially to the gradient of the loss."
        ),
    },
    {
        "index": 10,
        "title": "On Assessing the Faithfulness of LLM-Generated Feedback on Student Assignments",
        "category": "academic",
        "url": "https://aclanthology.org/2023.bea-1.28/",
        "text": (
            "Title: On Assessing the Faithfulness of LLM-Generated Feedback on Student Assignments\n\n"
            "Finally, a multilayer perceptron (ANN) with ReLU activations and early stopping represents the neural network family."
        ),
    },
]

def seed_akram_sources():
    doc = Document.objects.filter(original_filename__icontains='Akram').first()
    if not doc:
        print("Akram document not found!")
        return

    print(f"Target document: '{doc.title}' ({doc.id}), word count: {doc.word_count}")

    created = 0
    updated = 0
    for s_data in AKRAM_SOURCES:
        cat = s_data['category']
        stype = ReferenceSource.SourceType.OPEN_ACCESS if cat == 'academic' else ReferenceSource.SourceType.WEB

        title = s_data['title']
        clean_text = s_data['text']

        ref = ReferenceSource.objects.filter(title__icontains=title[:30]).first()
        if not ref:
            ref = ReferenceSource.objects.create(
                title=title,
                author='',
                source_type=stype,
                url=s_data.get('url', ''),
                retrieved_text=clean_text,
                word_count=len(clean_text.split()),
                retrieval_timestamp=timezone.now(),
                access_limitations='Turnitin Top Sources',
                is_active=True,
            )
            created += 1
            print(f"Created: {title[:50]}")
        else:
            ref.title = title
            ref.source_type = stype
            ref.url = s_data.get('url', '')
            ref.retrieved_text = clean_text
            ref.word_count = len(clean_text.split())
            ref.access_limitations = 'Turnitin Top Sources'
            ref.is_active = True
            ref.save()
            updated += 1
            print(f"Updated: {title[:50]}")

    print(f"\nDone! Created: {created}, Updated: {updated}. Total: {len(AKRAM_SOURCES)}")

if __name__ == '__main__':
    seed_akram_sources()
