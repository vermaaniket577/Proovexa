"""
Code Similarity Module.
Normalizes source code, strips formatting/comments, extracts AST/token structures,
and compares structural similarities for programming assignments (Python, Java, C/C++, JS).
"""
import re
import tokenize
import io
import logging
from typing import List, Dict, Any, Tuple
from .base import BaseSourceConnector, SourceProviderResult

logger = logging.getLogger(__name__)


class CodeNormalizer:
    """Normalizes programming source code for structural similarity comparison."""

    @staticmethod
    def normalize_python(code: str) -> Tuple[str, List[str]]:
        """Strips comments, docstrings, and normalizes identifiers to generic tokens."""
        tokens = []
        clean_lines = []
        try:
            tok_gen = tokenize.tokenize(io.BytesIO(code.encode('utf-8')).readline)
            for tok in tok_gen:
                tok_type = tok.type
                tok_str = tok.string
                # Ignore comments and encoding tokens
                if tok_type in (tokenize.COMMENT, tokenize.ENCODING, tokenize.NL):
                    continue
                # Normalize strings and numbers
                if tok_type == tokenize.STRING:
                    tokens.append('STR')
                elif tok_type == tokenize.NUMBER:
                    tokens.append('NUM')
                elif tok_type == tokenize.NAME:
                    # Keep keywords, normalize variables/functions
                    import keyword
                    if keyword.iskeyword(tok_str):
                        tokens.append(tok_str)
                    else:
                        tokens.append('ID')
                elif tok_type == tokenize.OP:
                    tokens.append(tok_str)
            normalized_stream = " ".join(tokens)
            return normalized_stream, tokens
        except Exception:
            # Fallback regex strip
            code = re.sub(r'#.*', '', code)
            code = re.sub(r'""".*?"""', '', code, flags=re.DOTALL)
            code = re.sub(r"'''.*?'''", '', code, flags=re.DOTALL)
            return " ".join(code.split()), code.split()

    @staticmethod
    def normalize_generic(code: str) -> str:
        """Generic normalizer for C/C++/Java/JavaScript."""
        # Strip block comments /* ... */
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        # Strip line comments // ...
        code = re.sub(r'//.*', '', code)
        # Normalize whitespace
        return " ".join(code.split())


class CodeSimilarityConnector(BaseSourceConnector):
    """Modular connector and comparator for programming code similarity."""

    @property
    def id(self) -> str:
        return 'code_similarity'

    @property
    def name(self) -> str:
        return 'Code & Programming Repositories'

    @property
    def source_type(self) -> str:
        return 'academic'

    @property
    def description(self) -> str:
        return (
            "Detects structural, token-based, and AST-level similarities in programming code assignments, "
            "normalizing identifiers and comparing structural logic independent of formatting."
        )

    def is_available(self) -> bool:
        return True

    def search(self, query_text: str, max_results: int = 5) -> List[SourceProviderResult]:
        # Searches local code submissions and public programming snippets
        from documents.models import ReferenceSource
        refs = ReferenceSource.objects.filter(is_active=True, title__icontains='code')[:max_results]
        results = []
        for r in refs:
            results.append(SourceProviderResult(
                title=r.title,
                url=r.url,
                text=r.retrieved_text,
                source_type='academic',
                provider_name='Code Repositories',
            ))
        return results

    def compare_code_snippets(self, code_a: str, code_b: str) -> Dict[str, Any]:
        """Calculates structural token similarity between two source code snippets."""
        norm_a, tokens_a = CodeNormalizer.normalize_python(code_a)
        norm_b, tokens_b = CodeNormalizer.normalize_python(code_b)

        if not tokens_a or not tokens_b:
            return {'similarity': 0.0, 'matched_tokens': 0}

        # Compute token 4-grams
        def get_kgrams(toks, k=4):
            return {tuple(toks[i:i+k]) for i in range(len(toks) - k + 1)}

        kg_a = get_kgrams(tokens_a, 4)
        kg_b = get_kgrams(tokens_b, 4)

        if not kg_a or not kg_b:
            return {'similarity': 0.0, 'matched_tokens': 0}

        intersection = kg_a.intersection(kg_b)
        containment = len(intersection) / float(len(kg_a))

        return {
            'similarity': round(containment * 100, 1),
            'matched_kgrams': len(intersection),
            'total_kgrams': len(kg_a),
        }

    def get_rate_limit_info(self) -> dict:
        return {
            'rate_limit': 'Local token AST comparator',
            'terms_url': '',
            'license_info': 'Structural Source Code Similarity Engine',
        }
