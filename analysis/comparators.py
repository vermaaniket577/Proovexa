"""
Individual comparison methods for similarity detection.
Each comparator is modular and independently configurable.
"""
import re
from collections import Counter, defaultdict
from .winnowing import WinnowingEngine
from difflib import SequenceMatcher
import logging

logger = logging.getLogger(__name__)


class ComparisonResult:
    """Result from a single comparison method."""

    def __init__(self, match_type):
        self.match_type = match_type
        self.matches = []  # List of match dicts
        self.similarity_score = 0.0

    def add_match(self, submitted_text, source_text, similarity, 
                  submitted_start=None, submitted_end=None, source_start=None, source_end=None,
                  submitted_page=1, submitted_para=1, source_page=None, source_para=None):
        self.matches.append({
            'submitted_text': submitted_text,
            'source_text': source_text,
            'similarity': similarity,
            'submitted_start': submitted_start,
            'submitted_end': submitted_end,
            'source_start': source_start,
            'source_end': source_end,
            'submitted_page': submitted_page,
            'submitted_para': submitted_para,
            'source_page': source_page,
            'source_para': source_para,
        })


class ExactMatchComparator:
    """
    Identify exact matching word sequences between documents.
    Exhaustively scans for contiguous word sequences of length >= min_word_count.
    Guarantees exact character offsets and original text formatting.
    """

    def __init__(self, min_word_count=8):
        self.min_word_count = min_word_count
        self._tokenizer = WinnowingEngine()

    def compare(self, submitted_text, source_text, submitted_pages=None, source_pages=None, sub_tokens=None, src_tokens=None):
        """Find exact matching sequences with exact character boundaries."""
        result = ComparisonResult('exact')

        if not submitted_text or not source_text:
            return result

        if sub_tokens is None:
            sub_tokens = self._tokenizer.tokenize_with_offsets(submitted_text)
        if src_tokens is None:
            src_tokens = self._tokenizer.tokenize_with_offsets(source_text)

        effective_min = min(self.min_word_count, len(src_tokens))
        if effective_min < 7 or len(sub_tokens) < effective_min:
            return result
        min_w = effective_min

        # Inverted index of source n-grams of size min_w
        src_index = defaultdict(list)
        for j in range(len(src_tokens) - min_w + 1):
            shing_key = tuple(t.clean_token for t in src_tokens[j:j + min_w])
            src_index[shing_key].append(j)

        # Contiguous exact matches scan across submitted tokens
        i = 0
        while i <= len(sub_tokens) - min_w:
            shing_key = tuple(t.clean_token for t in sub_tokens[i:i + min_w])
            if shing_key in src_index:
                # Find maximum forward extension among matching positions
                best_len = min_w
                best_j = src_index[shing_key][0]
                for j in src_index[shing_key]:
                    cur_len = min_w
                    while (i + cur_len < len(sub_tokens) and 
                           j + cur_len < len(src_tokens) and 
                           sub_tokens[i + cur_len].clean_token == src_tokens[j + cur_len].clean_token):
                        cur_len += 1
                    if cur_len > best_len:
                        best_len = cur_len
                        best_j = j

                sub_start = sub_tokens[i].start_char
                sub_end = sub_tokens[i + best_len - 1].end_char
                src_start = src_tokens[best_j].start_char
                src_end = src_tokens[best_j + best_len - 1].end_char

                matched_sub = submitted_text[sub_start:sub_end]
                matched_src = source_text[src_start:src_end]

                sub_page, sub_para = self._find_location(
                    submitted_pages, matched_sub
                ) if submitted_pages else (1, 1)

                src_page, src_para = self._find_location(
                    source_pages, matched_src
                ) if source_pages else (None, None)

                result.add_match(
                    submitted_text=matched_sub,
                    source_text=matched_src,
                    similarity=1.0,
                    submitted_start=sub_start,
                    submitted_end=sub_end,
                    source_start=src_start,
                    source_end=src_end,
                    submitted_page=sub_page,
                    submitted_para=sub_para,
                    source_page=src_page,
                    source_para=src_para,
                )

                # Advance past this match to ensure maximal non-overlapping intervals
                i += best_len
            else:
                i += 1

        if sub_tokens:
            total_matched_words = sum(
                len(m['submitted_text'].split()) for m in result.matches
            )
            result.similarity_score = min(1.0, total_matched_words / len(sub_tokens))

        return result

    def _normalize(self, text):
        """Normalize text for comparison."""
        text = text.lower()
        text = re.sub(r'[^\wऀ-ॿ\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _find_original_text(self, full_text, normalized_match):
        """Find the original (non-normalized) text corresponding to a normalized match."""
        words = normalized_match.split()
        if len(words) < 2:
            return normalized_match

        first_few = r'\s+'.join(re.escape(w) for w in words[:5])
        is_ascii = all(ord(c) < 128 for c in first_few)
        search_pattern = (r'' + first_few + r'') if is_ascii else (r'(?:^|\s|[^\wऀ-ॿ])' + first_few + r'(?:$|\s|[^\wऀ-ॿ])')
        match = re.search(search_pattern, full_text, re.IGNORECASE)
        if match:
            start = match.start()
            remaining = full_text[start:]
            word_spans = list(re.finditer(r'\S+', remaining))
            if len(word_spans) >= len(words):
                end = start + word_spans[len(words) - 1].end()
                return full_text[start:end]
        return normalized_match

    def _find_location(self, pages, text):
        """Find page and paragraph number for a text match."""
        if not pages:
            return 1, 1
        text_lower = text.lower()[:50]
        for page in pages:
            for para in page.get('paragraphs', []):
                if text_lower in para.get('text', '').lower():
                    return page['page_number'], para.get('para_number', 1)
        return 1, 1


class NGramComparator:
    """
    Compare overlapping word sequences (n-grams) to identify repeated phrases.
    """

    def __init__(self, n=5, min_matching_ngrams=3):
        self.n = n
        self.min_matching_ngrams = min_matching_ngrams

    def compare(self, submitted_text, source_text, submitted_pages=None, source_pages=None, sub_ngrams=None, src_ngrams=None, sub_words=None, src_words=None, sub_tokens=None, src_tokens=None):
        """Find matching n-gram sequences."""
        result = ComparisonResult('phrase')

        if sub_ngrams is None:
            sub_ngrams = self._extract_ngrams(submitted_text)
        if src_ngrams is None:
            src_ngrams = self._extract_ngrams(source_text)

        if not sub_ngrams or not src_ngrams:
            return result

        # Find common n-grams
        sub_set = set(sub_ngrams.keys())
        src_set = set(src_ngrams.keys())
        common = sub_set & src_set

        if len(common) < self.min_matching_ngrams:
            return result

        # Group consecutive matching n-grams into passages
        matched_passages = self._group_matches(common, sub_ngrams, src_ngrams,
                                                submitted_text, source_text,
                                                sub_words=sub_words, src_words=src_words)

        for passage in matched_passages:
            sub_page, sub_para = self._find_location(
                submitted_pages, passage['submitted_text']
            ) if submitted_pages else (1, 1)

            result.add_match(
                submitted_text=passage['submitted_text'],
                source_text=passage['source_text'],
                similarity=passage['similarity'],
                submitted_page=sub_page,
                submitted_para=sub_para,
            )

        if sub_ngrams:
            result.similarity_score = len(common) / len(sub_ngrams)

        return result

    def _extract_ngrams(self, text):
        """Extract word n-grams with positions."""
        words = self._tokenize(text)
        ngrams = {}
        for i in range(len(words) - self.n + 1):
            ngram = tuple(words[i:i + self.n])
            if ngram not in ngrams:
                ngrams[ngram] = []
            ngrams[ngram].append(i)
        return ngrams

    def _tokenize(self, text):
        """Tokenize text into words."""
        text = text.lower()
        text = re.sub(r'[^\w\u0900-\u097F\s]', '', text)
        return text.split()

    def _group_matches(self, common_ngrams, sub_ngrams, src_ngrams,
                       submitted_text, source_text, sub_words=None, src_words=None):
        """Group consecutive matching n-grams into larger passages."""
        passages = []

        # Sort common n-grams by their position in submitted text
        positioned = []
        for ngram in common_ngrams:
            for pos in sub_ngrams[ngram]:
                positioned.append((pos, ngram))
        positioned.sort()

        if not positioned:
            return passages

        # Group consecutive positions
        groups = []
        current_group = [positioned[0]]
        for i in range(1, len(positioned)):
            if positioned[i][0] - current_group[-1][0] <= self.n:
                current_group.append(positioned[i])
            else:
                if len(current_group) >= 1:
                    groups.append(current_group)
                current_group = [positioned[i]]
        if current_group:
            groups.append(current_group)

        # Convert groups to passages
        if sub_words is None:
            sub_words = self._tokenize(submitted_text)
        if src_words is None:
            src_words = self._tokenize(source_text)

        for group in groups:
            start_pos = group[0][0]
            end_pos = group[-1][0] + self.n
            sub_passage = ' '.join(sub_words[start_pos:end_pos])

            # Find corresponding source passage
            first_ngram = group[0][1]
            src_positions = src_ngrams.get(first_ngram, [])
            if src_positions:
                src_start = src_positions[0]
                src_end = src_start + (end_pos - start_pos)
                src_passage = ' '.join(src_words[src_start:min(src_end, len(src_words))])
            else:
                src_passage = sub_passage

            word_count = len(sub_passage.split())
            if word_count >= self.n:
                passages.append({
                    'submitted_text': sub_passage,
                    'source_text': src_passage,
                    'similarity': 0.9,  # N-gram matches are high confidence
                    'word_count': word_count,
                })

        return passages

    def _find_location(self, pages, text):
        if not pages:
            return 1, 1
        text_lower = text.lower()[:50]
        for page in pages:
            for para in page.get('paragraphs', []):
                if text_lower in para.get('text', '').lower():
                    return page['page_number'], para.get('para_number', 1)
        return 1, 1


class FuzzyComparator:
    """
    Identify similar wording while tolerating minor differences,
    punctuation changes, and limited word substitutions.
    """

    def __init__(self, threshold=0.75, min_sentence_length=6):
        self.threshold = threshold
        self.min_sentence_length = min_sentence_length

    def compare(self, submitted_text, source_text, submitted_pages=None, source_pages=None):
        """Find fuzzy matches between sentences."""
        result = ComparisonResult('fuzzy')

        sub_sentences = self._split_sentences(submitted_text)
        src_sentences = self._split_sentences(source_text)

        if not sub_sentences or not src_sentences:
            return result

        # Precompute tokens and token sets for source sentences
        src_data = []
        for src_sent in src_sentences:
            tokens = re.sub(r'[^\w\u0900-\u097F\s]', '', src_sent.lower()).split()
            if len(tokens) >= self.min_sentence_length:
                src_data.append((src_sent, tokens, len(tokens), set(tokens)))

        matched_count = 0
        for sub_sent in sub_sentences:
            sub_tokens_clean = re.sub(r'[^\w\u0900-\u097F\s]', '', sub_sent.lower()).split()
            sub_len = len(sub_tokens_clean)
            if sub_len < self.min_sentence_length:
                continue

            sub_set = set(sub_tokens_clean)
            best_match = None
            best_ratio = 0

            for src_sent, src_tokens, src_len, src_set in src_data:
                # Upper bound check: theoretical maximum ratio based on lengths
                if (2.0 * min(sub_len, src_len)) / (sub_len + src_len) < self.threshold:
                    continue
                # Upper bound check: theoretical maximum ratio based on shared vocabulary
                common_tokens = len(sub_set & src_set)
                if (2.0 * common_tokens) / (sub_len + src_len) < self.threshold:
                    continue

                ratio = SequenceMatcher(None, sub_tokens_clean, src_tokens).ratio()

                if ratio > best_ratio and ratio >= self.threshold and ratio < 1.0:
                    best_ratio = ratio
                    best_match = src_sent

            if best_match:
                matched_count += 1
                sub_page, sub_para = self._find_location(
                    submitted_pages, sub_sent
                ) if submitted_pages else (1, 1)

                result.add_match(
                    submitted_text=sub_sent,
                    source_text=best_match,
                    similarity=best_ratio,
                    submitted_page=sub_page,
                    submitted_para=sub_para,
                )

        if sub_sentences:
            result.similarity_score = matched_count / len(sub_sentences)

        return result

    def _split_sentences(self, text):
        """Split text into sentences."""
        sentences = re.split(r'[.!?।॥]+(?:\s+|$)', text)
        res = [s.strip() for s in sentences if len(s.strip().split()) >= self.min_sentence_length]
        if not res and text.strip() and len(text.strip().split()) >= self.min_sentence_length:
            return [text.strip()]
        return res

    def _find_location(self, pages, text):
        if not pages:
            return 1, 1
        text_lower = text.lower()[:50]
        for page in pages:
            for para in page.get('paragraphs', []):
                if text_lower in para.get('text', '').lower():
                    return page['page_number'], para.get('para_number', 1)
        return 1, 1


class TFIDFComparator:
    """
    Document-level similarity using TF-IDF and cosine similarity.
    Efficient for comparing against large reference collections.
    """

    def compare(self, submitted_text, source_text, submitted_pages=None, source_pages=None):
        """Calculate TF-IDF cosine similarity between two documents."""
        result = ComparisonResult('tfidf')

        if not submitted_text.strip() or not source_text.strip():
            return result

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            vectorizer = TfidfVectorizer(
                max_features=10000,
                stop_words='english',
                ngram_range=(1, 2),
                min_df=1,
            )
            tfidf_matrix = vectorizer.fit_transform([submitted_text, source_text])
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]

            result.similarity_score = float(similarity)

            if similarity > 0.1:
                result.add_match(
                    submitted_text=f"[Document-level similarity: {similarity:.2%}]",
                    source_text=f"[Document-level similarity with source]",
                    similarity=float(similarity),
                )

        except (Exception, MemoryError) as e:
            logger.error(f"TF-IDF comparison error: {e}")

        return result

    def compare_batch(self, submitted_text, source_texts):
        """
        Compare submitted document against multiple sources efficiently.
        Returns list of (source_index, similarity_score) tuples.
        """
        if not submitted_text.strip() or not source_texts:
            return []

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            all_texts = [submitted_text] + [s for s in source_texts if s.strip()]
            vectorizer = TfidfVectorizer(
                max_features=10000,
                stop_words='english',
                ngram_range=(1, 2),
                min_df=1,
            )
            tfidf_matrix = vectorizer.fit_transform(all_texts)
            similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]

            results = []
            for i, sim in enumerate(similarities):
                if sim > 0.005:  # Include fine-grained academic and web source overlaps
                    results.append((i, float(sim)))

            # Sort by similarity descending
            results.sort(key=lambda x: x[1], reverse=True)
            return results

        except (Exception, MemoryError) as e:
            logger.error(f"TF-IDF batch comparison error: {e}")
            return []
