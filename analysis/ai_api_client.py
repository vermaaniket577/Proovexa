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

    def __init__(self, ai_settings=None):
        self.reload_settings(ai_settings)

    def reload_settings(self, ai_settings=None):
        """Loads AI API settings dynamically from DB with fallback to settings.py."""
        if ai_settings is None:
            try:
                from .models import AIAPISettings
                ai_settings = AIAPISettings.get_settings()
            except Exception:
                ai_settings = None

        if ai_settings:
            self.is_enabled = bool(getattr(ai_settings, 'is_enabled', True))
            self.provider = getattr(ai_settings, 'provider', 'auto').lower()
            self.gemini_api_key = (getattr(ai_settings, 'gemini_api_key', '') or '').strip()
            self.gemini_model = getattr(ai_settings, 'gemini_model', 'gemini-1.5-flash').strip() or 'gemini-1.5-flash'
            self.openai_api_key = (getattr(ai_settings, 'openai_api_key', '') or '').strip()
            self.openai_model = getattr(ai_settings, 'openai_model', 'gpt-4o-mini').strip() or 'gpt-4o-mini'
            self.timeout = int(getattr(ai_settings, 'timeout_seconds', 15))
            self.temperature = float(getattr(ai_settings, 'temperature', 0.1))
            self.max_tokens = int(getattr(ai_settings, 'max_tokens', 2048))
            self.enable_ai_writing_detection = bool(getattr(ai_settings, 'enable_ai_writing_detection', True))
            self.enable_paraphrase_detection = bool(getattr(ai_settings, 'enable_paraphrase_detection', True))
            self.blend_weight = float(getattr(ai_settings, 'blend_weight', 0.5))
        else:
            self.is_enabled = True
            self.provider = getattr(settings, 'AI_API_PROVIDER', 'auto').lower()
            self.gemini_api_key = getattr(settings, 'GEMINI_API_KEY', '').strip()
            self.gemini_model = getattr(settings, 'GEMINI_MODEL', 'gemini-1.5-flash')
            self.openai_api_key = getattr(settings, 'OPENAI_API_KEY', '').strip()
            self.openai_model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
            self.timeout = getattr(settings, 'AI_API_TIMEOUT_SECONDS', 15)
            self.temperature = 0.1
            self.max_tokens = 2048
            self.enable_ai_writing_detection = True
            self.enable_paraphrase_detection = True
            self.blend_weight = 0.5

    def is_api_available(self, task_type: str = 'ai_writing') -> bool:
        """Returns True if external AI API calls are enabled and keys are configured for task."""
        if getattr(AIAPIClient, '_quota_exhausted', False):
            return False
        if not self.is_enabled or self.provider == 'local':
            return False
        if task_type == 'ai_writing' and not self.enable_ai_writing_detection:
            return False
        if task_type == 'paraphrase' and not self.enable_paraphrase_detection:
            return False

        if self.provider == 'gemini':
            return bool(self.gemini_api_key)
        elif self.provider == 'openai':
            return bool(self.openai_api_key)
        else:  # 'auto'
            return bool(self.gemini_api_key or self.openai_api_key)

    def get_active_provider_name(self) -> str:
        """Returns the human-readable name of the active detection provider."""
        if not self.is_enabled or self.provider == 'local':
            return "Calibrated Local AI Engine (Offline High-Accuracy Model)"
        if self.gemini_api_key and (self.provider in ('gemini', 'auto')):
            return f"Google Gemini API ({self.gemini_model})"
        elif self.openai_api_key and (self.provider in ('openai', 'auto')):
            return f"OpenAI API ({self.openai_model})"
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
        """Invokes Gemini REST API to analyze AI writing signals."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_api_key}"
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
            "generationConfig": {"temperature": self.temperature, "maxOutputTokens": self.max_tokens}
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code in (402, 429):
            AIAPIClient._quota_exhausted = True
            logger.warning(f"Gemini API quota exhausted (status {resp.status_code}). Switching to calibrated local AI engine.")
            return None
        if resp.status_code == 200:
            data = resp.json()
            raw_text = data['candidates'][0]['content']['parts'][0]['text']
            parsed = self._extract_json(raw_text)
            if parsed:
                parsed['provider'] = f"Google Gemini API ({self.gemini_model})"
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
            "model": self.openai_model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text[:4000]}
            ],
            "temperature": self.temperature,
            "response_format": {"type": "json_object"}
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code in (402, 429):
            AIAPIClient._quota_exhausted = True
            logger.warning(f"Gemini API quota exhausted (status {resp.status_code}). Switching to calibrated local AI engine.")
            return None
        if resp.status_code == 200:
            data = resp.json()
            content = data['choices'][0]['message']['content']
            parsed = json.loads(content)
            parsed['provider'] = f"OpenAI API ({self.openai_model})"
            return parsed
        return None

    def _fallback_local_ai_detection(self, text: str) -> Dict[str, Any]:
        """Runs offline calibrated statistical detection when no API key is supplied or API fails."""
        from .turnitin_ai_engine import TurnitinAIDetector
        detector = TurnitinAIDetector()
        result = detector.evaluate_document(text)

        sentence_evals = []
        for s in result.get('sentence_breakdown', []):
            cat = s.get('category', 'Human')
            sentence_evals.append({
                'sentence': s.get('sentence', ''),
                'category': 'ai_generated' if cat == 'AI-Generated' else ('ai_paraphrased' if cat == 'AI-Paraphrased' else 'human'),
                'confidence': s.get('ai_probability_pct', 50.0) / 100.0,
            })

        total_score = result.get('raw_total_ai_pct', 0.0)
        return {
            'provider': 'Calibrated Local AI Engine (Turnitin V2.5 Model)',
            'overall_ai_score': total_score,
            'ai_generated_pct': result.get('ai_generated_only_cyan_pct', 0.0),
            'ai_paraphrased_pct': result.get('ai_paraphrased_purple_pct', 0.0),
            'perplexity_assessment': 'Low (Uniform)' if total_score > 30 else 'High (Natural Variation)',
            'burstiness_assessment': 'Uniform Syntax' if total_score > 30 else 'Varied Human Rhythm',
            'summary': (
                f"Evaluated with calibrated statistical engine across {result.get('document_metrics', {}).get('qualifying_word_count', 0)} qualifying prose words. "
                f"Cyan (AI-Generated): {result.get('ai_generated_only_cyan_pct', 0.0)}%, "
                f"Purple (AI-Paraphrased): {result.get('ai_paraphrased_purple_pct', 0.0)}%."
            ),
            'sentence_evaluations': sentence_evals,
            'is_fallback': True,
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
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_api_key}"
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
            "generationConfig": {"temperature": self.temperature, "maxOutputTokens": self.max_tokens}
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code in (402, 429):
            AIAPIClient._quota_exhausted = True
            logger.warning(f"Gemini API quota exhausted (status {resp.status_code}). Switching to calibrated local AI engine.")
            return None
        if resp.status_code == 200:
            raw = resp.json()['candidates'][0]['content']['parts'][0]['text']
            parsed = self._extract_json(raw)
            if parsed:
                parsed['provider'] = f"Google Gemini API (Semantic Paraphrase Engine - {self.gemini_model})"
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
            "model": self.openai_model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"SUBMISSION:\n{sub_text[:2500]}\n\nSOURCE:\n{src_text[:2500]}"}
            ],
            "temperature": self.temperature,
            "response_format": {"type": "json_object"}
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code in (402, 429):
            AIAPIClient._quota_exhausted = True
            logger.warning(f"Gemini API quota exhausted (status {resp.status_code}). Switching to calibrated local AI engine.")
            return None
        if resp.status_code == 200:
            parsed = json.loads(resp.json()['choices'][0]['message']['content'])
            parsed['provider'] = f"OpenAI API (Semantic Paraphrase Engine - {self.openai_model})"
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

    def test_connection(self, provider: Optional[str] = None, api_key: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
        """
        Tests live API connectivity and credentials.
        Returns:
            Dict containing success (bool), latency_ms (int), provider (str), model (str), message (str), error (str).
        """
        import time
        target_provider = (provider or self.provider or 'gemini').lower()
        if target_provider == 'auto':
            target_provider = 'gemini' if (api_key or self.gemini_api_key) else 'openai'

        start_time = time.time()

        if target_provider == 'gemini':
            key = (api_key or self.gemini_api_key).strip()
            mdl = (model or self.gemini_model).strip() or 'gemini-1.5-flash'
            if not key:
                return {
                    'success': False,
                    'provider': 'Google Gemini API',
                    'model': mdl,
                    'latency_ms': 0,
                    'error': 'No Gemini API key provided. Please enter a valid API key.'
                }

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:generateContent?key={key}"
            payload = {
                "contents": [{"parts": [{"text": "Ping test. Respond with valid JSON only: {\"status\": \"ok\", \"service\": \"gemini\"}"}]}],
                "generationConfig": {"temperature": 0.0, "maxOutputTokens": 64}
            }
            headers = {'Content-Type': 'application/json'}
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                latency = int((time.time() - start_time) * 1000)
                if resp.status_code == 200:
                    return {
                        'success': True,
                        'provider': 'Google Gemini API',
                        'model': mdl,
                        'latency_ms': latency,
                        'message': f"Connected successfully to Google Gemini ({mdl}) in {latency}ms."
                    }
                else:
                    err_msg = f"HTTP {resp.status_code}"
                    try:
                        err_data = resp.json()
                        err_msg = err_data.get('error', {}).get('message', err_msg)
                    except Exception:
                        err_msg = resp.text[:200]
                    return {
                        'success': False,
                        'provider': 'Google Gemini API',
                        'model': mdl,
                        'latency_ms': latency,
                        'error': f"Gemini API returned error: {err_msg}"
                    }
            except requests.Timeout:
                return {
                    'success': False,
                    'provider': 'Google Gemini API',
                    'model': mdl,
                    'latency_ms': int((time.time() - start_time) * 1000),
                    'error': f"Connection timed out after {self.timeout} seconds."
                }
            except Exception as e:
                return {
                    'success': False,
                    'provider': 'Google Gemini API',
                    'model': mdl,
                    'latency_ms': int((time.time() - start_time) * 1000),
                    'error': f"Connection failed: {str(e)}"
                }

        elif target_provider == 'openai':
            key = (api_key or self.openai_api_key).strip()
            mdl = (model or self.openai_model).strip() or 'gpt-4o-mini'
            if not key:
                return {
                    'success': False,
                    'provider': 'OpenAI API',
                    'model': mdl,
                    'latency_ms': 0,
                    'error': 'No OpenAI API key provided. Please enter a valid API key.'
                }

            url = "https://api.openai.com/v1/chat/completions"
            payload = {
                "model": mdl,
                "messages": [
                    {"role": "user", "content": "Ping test. Respond with valid JSON: {\"status\": \"ok\"}"}
                ],
                "max_tokens": 32,
                "temperature": 0.0,
            }
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {key}'
            }
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                latency = int((time.time() - start_time) * 1000)
                if resp.status_code == 200:
                    return {
                        'success': True,
                        'provider': 'OpenAI API',
                        'model': mdl,
                        'latency_ms': latency,
                        'message': f"Connected successfully to OpenAI ({mdl}) in {latency}ms."
                    }
                else:
                    err_msg = f"HTTP {resp.status_code}"
                    try:
                        err_data = resp.json()
                        err_msg = err_data.get('error', {}).get('message', err_msg)
                    except Exception:
                        err_msg = resp.text[:200]
                    return {
                        'success': False,
                        'provider': 'OpenAI API',
                        'model': mdl,
                        'latency_ms': latency,
                        'error': f"OpenAI API returned error: {err_msg}"
                    }
            except requests.Timeout:
                return {
                    'success': False,
                    'provider': 'OpenAI API',
                    'model': mdl,
                    'latency_ms': int((time.time() - start_time) * 1000),
                    'error': f"Connection timed out after {self.timeout} seconds."
                }
            except Exception as e:
                return {
                    'success': False,
                    'provider': 'OpenAI API',
                    'model': mdl,
                    'latency_ms': int((time.time() - start_time) * 1000),
                    'error': f"Connection failed: {str(e)}"
                }

        else:
            return {
                'success': True,
                'provider': 'Calibrated Local AI Engine',
                'model': 'Turnitin V2.5 Calibrated Offline Model',
                'latency_ms': 0,
                'message': 'Local Calibrated AI Engine is active (offline mode; no external API credentials needed).'
            }


    # =========================================================================
    # 3. TURNITIN SIMILARITY & SOURCE ATTRIBUTION API ENGINE
    # =========================================================================
    def evaluate_turnitin_similarity(
        self,
        submitted_text: str,
        retrieved_sources: Optional[List[Dict[str, Any]]] = None,
        use_search_grounding: bool = True
    ) -> Dict[str, Any]:
        """
        Executes Turnitin Match Overview and Enhanced Similarity Analysis:
        - Cross-references submitted text against candidate sources or live search
        - Categorizes matches into 4 Turnitin Match Groups:
          NOT_CITED_OR_QUOTED, MISSING_QUOTATION, MISSING_CITATION, CITED_AND_QUOTED
        - Aggregates source percentages in descending order with match numbers [1], [2], ...
        - Returns strict Turnitin JSON Schema
        """
        if not submitted_text or not submitted_text.strip():
            return {
                "overall_similarity_percentage": 0.0,
                "similarity_excluding_quoted_and_cited": 0.0,
                "match_groups_summary": {
                    "not_cited_or_quoted_count": 0,
                    "missing_quotation_count": 0,
                    "missing_citation_count": 0,
                    "cited_and_quoted_count": 0
                },
                "sources_overview": [],
                "highlighted_matches": []
            }

        # Auto-retrieve candidate sources via Playwright/Academic engines if none supplied
        if retrieved_sources is None:
            try:
                from .playwright_scraper import PlaywrightPlagiarismChecker
                scraper = PlaywrightPlagiarismChecker(headless=True, timeout_ms=10000)
                web_refs = scraper.search_and_retrieve_sources(submitted_text, min_words=14, max_sources=6)
                retrieved_sources = [
                    {
                        'source_id': str(r.id),
                        'title': r.title,
                        'url': getattr(r, 'url', '') or '',
                        'source_type': r.get_source_type_display(),
                        'snippet': (r.retrieved_text or '')[:1000]
                    }
                    for r in web_refs
                ]
            except Exception as e:
                logger.warning(f"Turnitin similarity auto source retrieval skipped: {e}")
                retrieved_sources = []

        # Split document into numbered sentences
        raw_sentences = [s.strip() for s in re.split(r'(?<=[.!?।॥\n])\s+', submitted_text) if s.strip()]
        numbered_sentences = [{"sentence_index": idx + 1, "text": s} for idx, s in enumerate(raw_sentences)]

        # Try Google Gemini with Search Grounding or retrieved sources
        if self.gemini_api_key and (self.provider in ('gemini', 'auto')):
            try:
                res = self._call_gemini_turnitin_engine(submitted_text, numbered_sentences, retrieved_sources, use_search_grounding)
                if res and "sources_overview" in res:
                    return res
            except Exception as ge:
                logger.warning(f"Gemini Turnitin API call failed: {ge}. Using fallback.")

        # Try OpenAI API with structured response
        if self.openai_api_key and (self.provider in ('openai', 'auto')):
            try:
                res = self._call_openai_turnitin_engine(submitted_text, numbered_sentences, retrieved_sources)
                if res and "sources_overview" in res:
                    return res
            except Exception as oe:
                logger.warning(f"OpenAI Turnitin API call failed: {oe}. Using fallback.")

        # Local calibrated Turnitin Match Groups Engine
        return self._local_turnitin_similarity_fallback(submitted_text, raw_sentences, retrieved_sources)

    def _call_gemini_turnitin_engine(
        self,
        full_text: str,
        numbered_sentences: List[Dict[str, Any]],
        retrieved_sources: List[Dict[str, Any]],
        use_search_grounding: bool
    ) -> Optional[Dict[str, Any]]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_api_key}"
        sys_prompt = (
            "You are the Turnitin Similarity & Source Attribution API Engine.\n"
            "Analyze submitted_text against retrieved_sources or web grounding.\n"
            "Categorize matches into 4 official Turnitin Match Groups: "
            "NOT_CITED_OR_QUOTED, MISSING_QUOTATION, MISSING_CITATION, CITED_AND_QUOTED.\n"
            "Classify match_type as: Verbatim (8+ words), Mosaic_Patchwriting, Structural_Paraphrase.\n"
            "Calculate per-source similarity_percentage = (matched_words / total_words) * 100.\n"
            "Sort sources_overview in descending order by percentage, assigning sequential match_number (1, 2, ...).\n"
            "Output STRICT JSON ONLY adhering to the requested schema."
        )
        user_content = {
            "submitted_text": numbered_sentences[:60],
            "retrieved_sources": retrieved_sources[:8]
        }
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{
                "parts": [
                    {"text": sys_prompt},
                    {"text": json.dumps(user_content, ensure_ascii=False)}
                ]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": self.max_tokens,
                "responseMimeType": "application/json"
            }
        }
        if use_search_grounding:
            payload["tools"] = [{"google_search": {}}]

        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code in (402, 429):
            AIAPIClient._quota_exhausted = True
            logger.warning(f"Gemini API quota exhausted (status {resp.status_code}). Switching to calibrated local AI engine.")
            return None
        if resp.status_code == 200:
            raw = resp.json()['candidates'][0]['content']['parts'][0]['text']
            return self._extract_json(raw)
        return None

    def _call_openai_turnitin_engine(
        self,
        full_text: str,
        numbered_sentences: List[Dict[str, Any]],
        retrieved_sources: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        url = "https://api.openai.com/v1/chat/completions"
        sys_prompt = (
            "You are the Turnitin Similarity & Source Attribution API Engine. "
            "Cross-reference submitted_text with retrieved_sources. "
            "Categorize each flagged passage into one of 4 Turnitin Match Groups: "
            "NOT_CITED_OR_QUOTED, MISSING_QUOTATION, MISSING_CITATION, CITED_AND_QUOTED. "
            "Match types: Verbatim, Mosaic_Patchwriting, Structural_Paraphrase. "
            "Return JSON matching the Turnitin output schema with overall_similarity_percentage, "
            "similarity_excluding_quoted_and_cited, match_groups_summary, sources_overview (sorted descending), "
            "and highlighted_matches."
        )
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.openai_api_key}'
        }
        payload = {
            "model": self.openai_model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": json.dumps({"submitted_text": numbered_sentences[:60], "retrieved_sources": retrieved_sources[:8]}, ensure_ascii=False)}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code in (402, 429):
            AIAPIClient._quota_exhausted = True
            logger.warning(f"Gemini API quota exhausted (status {resp.status_code}). Switching to calibrated local AI engine.")
            return None
        if resp.status_code == 200:
            return json.loads(resp.json()['choices'][0]['message']['content'])
        return None

    def _local_turnitin_similarity_fallback(
        self,
        submitted_text: str,
        sentences: List[str],
        retrieved_sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calibrated offline fallback implementation of Turnitin 4-Match-Group Similarity Engine.
        """
        from .winnowing import WinnowingEngine
        tokenizer = WinnowingEngine()
        sub_tokens = tokenizer.tokenize_with_offsets(submitted_text)
        total_words = max(len(sub_tokens), 1)

        source_word_sets: Dict[str, set] = {}
        source_meta: Dict[str, Dict[str, Any]] = {}
        for s in (retrieved_sources or []):
            sid = str(s.get('source_id') or s.get('title') or len(source_meta) + 1)
            source_meta[sid] = {
                'source_id': sid,
                'title': s.get('title', f"Source {len(source_meta)+1}"),
                'url': s.get('url', ''),
                'source_type': s.get('source_type', 'Internet Source'),
                'snippet': s.get('snippet', '')
            }
            src_text = s.get('snippet') or s.get('text') or ''
            src_clean = set(re.findall(r'[\w\u0900-\u097F]+', src_text.lower()))
            source_word_sets[sid] = src_clean

        highlighted_matches = []
        source_matched_words: Dict[str, set] = {sid: set() for sid in source_meta}
        not_cited_count = 0
        missing_quote_count = 0
        missing_cite_count = 0
        cited_quote_count = 0

        char_cursor = 0
        for sent in sentences:
            sent_len = len(sent)
            start_pos = submitted_text.find(sent, char_cursor)
            if start_pos == -1:
                start_pos = char_cursor
            end_pos = start_pos + sent_len
            char_cursor = end_pos

            sent_words = re.findall(r'[\w\u0900-\u097F]+', sent.lower())
            if len(sent_words) < 8:
                continue

            # Determine citation & quotation status
            has_citation = bool(
                re.search(r'\([\w\s,]+,\s*\d{4}', sent) or
                re.search(r'\(\w+\s+et\s+al\.,?\s*\d{4}\)', sent) or
                re.search(r'\[\d+\]', sent)
            )
            has_quotes = bool(
                sent.strip().startswith(('"', '“', "'", '‘')) or
                sent.strip().endswith(('"', '”', "'", '’')) or
                ('"' in sent) or ('“' in sent)
            )

            if has_quotes and has_citation:
                match_group = "CITED_AND_QUOTED"
            elif has_quotes and not has_citation:
                match_group = "MISSING_CITATION"
            elif has_citation and not has_quotes:
                match_group = "MISSING_QUOTATION"
            else:
                match_group = "NOT_CITED_OR_QUOTED"

            # Check match against candidate sources
            sent_word_set = set(sent_words)
            best_sid = None
            best_overlap = 0.0

            for sid, src_words in source_word_sets.items():
                if not src_words:
                    continue
                overlap = len(sent_word_set & src_words) / max(len(sent_word_set), 1)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_sid = sid

            if best_sid and best_overlap >= 0.60:
                match_type = "Verbatim" if best_overlap >= 0.85 else "Mosaic_Patchwriting"
                src_info = source_meta[best_sid]
                
                # Attribute word indices
                for idx, t in enumerate(sub_tokens):
                    if start_pos <= t.start_char and t.end_char <= end_pos:
                        source_matched_words[best_sid].add(idx)

                highlighted_matches.append({
                    "match_number": 0,  # Updated after ranking
                    "match_group": match_group,
                    "match_type": match_type,
                    "submitted_span": {
                        "text": sent,
                        "start_char": start_pos,
                        "end_char": end_pos
                    },
                    "source_span": {
                        "matched_source_text": src_info['snippet'][:250] if src_info['snippet'] else sent,
                        "source_title": src_info['title'],
                        "source_url": src_info['url']
                    },
                    "_source_id": best_sid
                })

                if match_group == "NOT_CITED_OR_QUOTED":
                    not_cited_count += 1
                elif match_group == "MISSING_QUOTATION":
                    missing_quote_count += 1
                elif match_group == "MISSING_CITATION":
                    missing_cite_count += 1
                elif match_group == "CITED_AND_QUOTED":
                    cited_quote_count += 1

        # Rank sources descending by percentage
        all_matched_word_indices = set()
        uncited_matched_word_indices = set()

        sources_overview = []
        for sid, matched_indices in source_matched_words.items():
            if not matched_indices:
                continue
            all_matched_word_indices.update(matched_indices)
            pct = round((len(matched_indices) / total_words) * 100, 2)
            s_info = source_meta[sid]
            sources_overview.append({
                "source_id": sid,
                "source_title": s_info['title'],
                "source_url": s_info['url'],
                "source_type": s_info['source_type'],
                "source_similarity_percentage": pct,
                "total_matches_in_document": sum(1 for m in highlighted_matches if m.get('_source_id') == sid)
            })

        sources_overview.sort(key=lambda s: s['source_similarity_percentage'], reverse=True)
        sid_to_match_num = {}
        for rank, s in enumerate(sources_overview, 1):
            s['match_number'] = rank
            sid_to_match_num[s['source_id']] = rank

        for m in highlighted_matches:
            sid = m.pop('_source_id', None)
            m['match_number'] = sid_to_match_num.get(sid, 1)

        for m in highlighted_matches:
            if m['match_group'] != "CITED_AND_QUOTED":
                for idx, t in enumerate(sub_tokens):
                    if m['submitted_span']['start_char'] <= t.start_char and t.end_char <= m['submitted_span']['end_char']:
                        uncited_matched_word_indices.add(idx)

        overall_sim = round((len(all_matched_word_indices) / total_words) * 100, 2)
        uncited_sim = round((len(uncited_matched_word_indices) / total_words) * 100, 2)

        return {
            "overall_similarity_percentage": overall_sim,
            "similarity_excluding_quoted_and_cited": uncited_sim,
            "match_groups_summary": {
                "not_cited_or_quoted_count": not_cited_count,
                "missing_quotation_count": missing_quote_count,
                "missing_citation_count": missing_cite_count,
                "cited_and_quoted_count": cited_quote_count
            },
            "sources_overview": sources_overview,
            "highlighted_matches": highlighted_matches
        }
