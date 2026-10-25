"""
Universal AI API Client for Plagiarism & AI-Generated Writing Detection.
Supports:
1. Google Gemini API (gemini-1.5-flash)
2. OpenAI API (gpt-4o-mini / gpt-4o)
3. Robust Fallback to Calibrated Local Engine when offline or no API key is provided.
"""
import re
import json
import logging
import requests
from typing import Dict, Any, List, Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class AIAPIClient:
    """
    Connects to external AI APIs (Google Gemini, OpenAI) to perform:
    - High-precision AI writing detection and sentence-level categorization
    - Advanced semantic paraphrase & synonym-spun plagiarism detection
    """

    def __init__(self):
        self.gemini_api_key = getattr(settings, 'GEMINI_API_KEY', '').strip()
        self.openai_api_key = getattr(settings, 'OPENAI_API_KEY', '').strip()
        self.provider = getattr(settings, 'AI_API_PROVIDER', 'auto').lower()
        self.timeout = getattr(settings, 'AI_API_TIMEOUT_SECONDS', 15)

    def is_api_available(self) -> bool:
        """Returns True if at least one valid external AI API key is configured."""
        if self.provider == 'gemini':
            return bool(self.gemini_api_key)
        elif self.provider == 'openai':
            return bool(self.openai_api_key)
        else:  # 'auto'
            return bool(self.gemini_api_key or self.openai_api_key)

    def get_active_provider_name(self) -> str:
        """Returns the human-readable name of the active detection provider."""
        if self.gemini_api_key and (self.provider in ('gemini', 'auto')):
            return "Google Gemini API (gemini-1.5-flash)"
        elif self.openai_api_key and (self.provider in ('openai', 'auto')):
            return "OpenAI API (gpt-4o-mini)"
        return "Calibrated Local AI Engine (Offline High-Accuracy Model)"

    # =========================================================================
    # 1. AI WRITING DETECTION VIA AI API
    # =========================================================================
    def detect_ai_writing(self, text: str) -> Dict[str, Any]:
        """
        Uses configured AI API to evaluate prose for AI authorship characteristics.
        Distinguishes between:
        - Cyan: Entirely AI-Generated (Low Perplexity, Uniform Burstiness)
        - Purple: AI-Paraphrased / Synonym Spun (QuillBot / Spinner signatures)
        - Human: Natural human variation and stylistic idiosyncrasy
        """
        if not text or len(text.strip().split()) < 30:
            return {
                'provider': self.get_active_provider_name(),
                'overall_ai_score': 0.0,
                'ai_generated_pct': 0.0,
                'ai_paraphrased_pct': 0.0,
                'sentence_evaluations': [],
                'summary': "Document has fewer than qualifying words for AI detection.",
            }

        # Try Google Gemini if available
        if self.gemini_api_key and (self.provider in ('gemini', 'auto')):
            try:
                res = self._call_gemini_ai_detector(text)
                if res:
                    return res
            except Exception as e:
                logger.warning(f"Gemini AI API detection call failed: {e}. Trying fallback.")

        # Try OpenAI if available
        if self.openai_api_key and (self.provider in ('openai', 'auto')):
            try:
                res = self._call_openai_ai_detector(text)
                if res:
                    return res
            except Exception as e:
                logger.warning(f"OpenAI detection call failed: {e}. Trying fallback.")

        # Fallback to local calibrated engine
        return self._fallback_local_ai_detection(text)

    def _call_gemini_ai_detector(self, text: str) -> Optional[Dict[str, Any]]:
        """Invokes Gemini 1.5 Flash REST API to analyze AI writing signals."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
        prompt = (
            "You are an academic forensic NLP specialist. Analyze the following academic text for AI generation signals "
            "(syntactic predictability, perplexity uniformity, characteristic LLM transition phrases, and synonym-spinning). "
            "Output ONLY valid JSON in this exact structure without markdown fences:\n"
            "{\n"
            '  "overall_ai_score": <number 0-100>,\n'
            '  "ai_generated_pct": <number 0-100>,\n'
            '  "ai_paraphrased_pct": <number 0-100>,\n'
            '  "perplexity_assessment": "<Low (Predictable) | Moderate | High (Human)>",\n'
            '  "burstiness_assessment": "<Uniform | Varied>",\n'
            '  "summary": "<1-2 sentences explainable summary>",\n'
            '  "sentence_evaluations": [\n'
            '     {"sentence": "<exact text>", "category": "<ai_generated|ai_paraphrased|human>", "confidence": <0.0-1.0>}\n'
            '  ]\n'
            "}\n\n"
            f"TEXT TO EVALUATE:\n{text[:4000]}"
        )

        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048}
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code == 200:
            data = resp.json()
            raw_text = data['candidates'][0]['content']['parts'][0]['text']
            parsed = self._extract_json(raw_text)
            if parsed:
                parsed['provider'] = "Google Gemini API (gemini-1.5-flash)"
                return parsed
        return None

    def _call_openai_ai_detector(self, text: str) -> Optional[Dict[str, Any]]:
        """Invokes OpenAI Chat Completion API to analyze AI writing signals."""
        url = "https://api.openai.com/v1/chat/completions"
        prompt = (
            "Analyze the following academic submission for AI generation vs Human writing. "
            "Return valid JSON with keys: overall_ai_score (0-100), ai_generated_pct (0-100), "
            "ai_paraphrased_pct (0-100), perplexity_assessment, burstiness_assessment, summary, "
            "and sentence_evaluations (list of {sentence, category: ai_generated|ai_paraphrased|human, confidence})."
        )
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.openai_api_key}'
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text[:4000]}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code == 200:
            data = resp.json()
            content = data['choices'][0]['message']['content']
            parsed = json.loads(content)
            parsed['provider'] = "OpenAI API (gpt-4o-mini)"
            return parsed
        return None

    def _fallback_local_ai_detection(self, text: str) -> Dict[str, Any]:
        """Runs offline calibrated statistical detection when no API key is supplied."""
        from .turnitin_ai_engine import TurnitinAIDetector
        detector = TurnitinAIDetector()
        result = detector.evaluate_document(text)

        sentence_evals = []
        for s in result.get('sentence_breakdown', []):
            cat = s.get('category', 'human')
            sentence_evals.append({
                'sentence': s.get('sentence', ''),
                'category': 'ai_generated' if cat == 'ai_generated_only' else ('ai_paraphrased' if cat == 'ai_paraphrased' else 'human'),
                'confidence': s.get('confidence', 0.5),
            })

        return {
            'provider': 'Calibrated Local AI Engine (Turnitin V2.0 Model)',
            'overall_ai_score': result.get('raw_overall_ai_pct', 0.0),
            'ai_generated_pct': result.get('ai_generated_only_cyan_pct', 0.0),
            'ai_paraphrased_pct': result.get('ai_paraphrased_purple_pct', 0.0),
            'perplexity_assessment': 'Low (Uniform)' if result.get('raw_overall_ai_pct', 0) > 30 else 'High (Natural Variation)',
            'burstiness_assessment': 'Uniform Syntax' if result.get('raw_overall_ai_pct', 0) > 30 else 'Varied Human Rhythm',
            'summary': (
                f"Evaluated with calibrated statistical engine across {result.get('qualifying_word_count', 0)} qualifying prose words. "
                f"Cyan (AI-Generated): {result.get('ai_generated_only_cyan_pct', 0.0)}%, "
                f"Purple (AI-Paraphrased): {result.get('ai_paraphrased_purple_pct', 0.0)}%."
            ),
            'sentence_evaluations': sentence_evals,
        }

    # =========================================================================
    # 2. SEMANTIC PARAPHRASE PLAGIARISM DETECTION VIA AI API
    # =========================================================================
    def detect_semantic_plagiarism(self, submitted_text: str, source_text: str) -> Dict[str, Any]:
        """
        Detects disguised plagiarism: synonym swapping, active/passive voice transformation,
        and AI-assisted paraphrasing between submitted text and a source text.
        """
        if self.gemini_api_key and (self.provider in ('gemini', 'auto')):
            try:
                res = self._call_gemini_paraphrase_detector(submitted_text, source_text)
                if res:
                    return res
            except Exception as e:
                logger.warning(f"Gemini paraphrase API failed: {e}")

        if self.openai_api_key and (self.provider in ('openai', 'auto')):
            try:
                res = self._call_openai_paraphrase_detector(submitted_text, source_text)
                if res:
                    return res
            except Exception as e:
                logger.warning(f"OpenAI paraphrase API failed: {e}")

        # Local fallback using TF-IDF and S-BERT hybrid checker
        return self._fallback_local_paraphrase_detection(submitted_text, source_text)

    def _call_gemini_paraphrase_detector(self, sub_text: str, src_text: str) -> Optional[Dict[str, Any]]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
        prompt = (
            "You are an academic similarity auditor. Compare SUBMISSION and SOURCE to detect paraphrased plagiarism. "
            "Output JSON with keys: is_paraphrase (bool), semantic_similarity (float 0.0-1.0), "
            "paraphrase_type (string, e.g. 'Synonym Swapping', 'Sentence Restructuring', or 'None'), "
            "explanation (detailed string), and matched_pairs (list of {sub_passage, src_passage, similarity}).\n\n"
            f"SUBMISSION:\n{sub_text[:2500]}\n\nSOURCE:\n{src_text[:2500]}"
        )
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048}
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code == 200:
            raw = resp.json()['candidates'][0]['content']['parts'][0]['text']
            parsed = self._extract_json(raw)
            if parsed:
                parsed['provider'] = "Google Gemini API (Semantic Paraphrase Engine)"
                return parsed
        return None

    def _call_openai_paraphrase_detector(self, sub_text: str, src_text: str) -> Optional[Dict[str, Any]]:
        url = "https://api.openai.com/v1/chat/completions"
        prompt = (
            "Compare the submitted passage against the reference source for semantic plagiarism and rewrites. "
            "Return JSON with: is_paraphrase (bool), semantic_similarity (0.0-1.0), paraphrase_type, explanation, "
            "and matched_pairs (list of {sub_passage, src_passage, similarity})."
        )
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.openai_api_key}'
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"SUBMISSION:\n{sub_text[:2500]}\n\nSOURCE:\n{src_text[:2500]}"}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code == 200:
            parsed = json.loads(resp.json()['choices'][0]['message']['content'])
            parsed['provider'] = "OpenAI API (Semantic Paraphrase Engine)"
            return parsed
        return None

    def _fallback_local_paraphrase_detection(self, sub_text: str, src_text: str) -> Dict[str, Any]:
        """Local 3-tier hybrid checker fallback."""
        from .hybrid_checker import TurnitinStyleChecker
        checker = TurnitinStyleChecker()
        res = checker.evaluate(sub_text, src_text)
        is_paraphrase = res['semantic_paraphrase_pct'] > 30.0 or res['composite_similarity_pct'] > 40.0
        return {
            'provider': 'Calibrated Local 3-Tier Hybrid Engine',
            'is_paraphrase': is_paraphrase,
            'semantic_similarity': round(res['semantic_paraphrase_pct'] / 100.0, 3),
            'composite_similarity_pct': res['composite_similarity_pct'],
            'paraphrase_type': 'Synonym & Structural Overlap' if is_paraphrase else 'None',
            'explanation': (
                f"Evaluated via Local Hybrid Pipeline: {res['exact_shingle_containment_pct']}% exact shingle containment, "
                f"{res['lexical_tfidf_pct']}% TF-IDF lexical overlap, and {res['semantic_paraphrase_pct']}% semantic paraphrase match."
            ),
            'matched_pairs': [
                {'sub_passage': m['submitted_sentence'], 'src_passage': m['source_sentence'], 'similarity': m['semantic_similarity']}
                for m in res.get('flagged_sentences', [])
            ]
        }

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        """Cleans and extracts JSON object from raw LLM output string."""
        try:
            # Strip markdown code blocks if present
            clean = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.MULTILINE)
            clean = re.sub(r'```$', '', clean.strip(), flags=re.MULTILINE)
            match = re.search(r'(\{[\s\S]*\})', clean)
            if match:
                return json.loads(match.group(1))
            return json.loads(clean)
        except Exception as e:
            logger.debug(f"JSON parse error from LLM response: {e}")
            return None
