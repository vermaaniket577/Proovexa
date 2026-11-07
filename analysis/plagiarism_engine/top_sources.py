"""
Top Sources Overlap Resolution Algorithm (Greedy Weighted Set Cover).
======================================================================
Turnitin and industrial academic plagiarism reports enforce a critical constraint:
"Overlapping sources will not be displayed."

If Sentence A matches Source 1 (MDPI) and Source 2 (Course Hero), that segment
must only be credited to the primary source so the total percentage does not exceed 100%.

Algorithm:
1. Raw Match Collection: Collect all matched spans per candidate source.
2. Source Weight Calculation: RawWeight(S) = sum(unique tokens matched with Source S).
3. Iterative Greedy Assignment:
   - Sort candidate sources by remaining unique eligible token count in descending order.
   - Assign highest source as Top Source #1.
   - Mark its tokens as CLAIMED.
   - For all remaining sources, subtract any spans overlapping with CLAIMED tokens.
   - Recalculate remaining unique token counts.
   - Pick next highest as Top Source #2. Repeat until no matches remain or length < min threshold.
4. Non-Overlapping Span Annotation: Disjoint character spans assigned to winning source rank.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple, Union
from .ingestion import TokenSpan
from .fingerprinting import RawMatch
from .exclusions import ExclusionFiltersEngine


@dataclass
class TopSourceItem:
    """Represents an attributed non-overlapping Top Source in the plagiarism report."""
    rank: int
    source_id: str
    source_name: str
    source_type: str   # 'Internet', 'Publication', 'Submitted works'
    similarity_percent: Union[int, str]  # e.g. 1, 2 or "<1%"
    matched_word_count: int
    source_url: str = ""
    attributed_tokens: Set[int] = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "similarity_percent": self.similarity_percent,
            "matched_word_count": self.matched_word_count,
        }


@dataclass
class AnnotatedDocumentSpan:
    """Disjoint highlighted manuscript span attributed to a specific Top Source rank."""
    span_id: int
    source_rank: int
    start_char: int
    end_char: int
    text_snippet: str
    source_url: str
    classification: str  # 'not_cited_or_quoted', 'missing_quotations', 'missing_citation', 'cited_and_quoted'
    token_start: int = 0
    token_end: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "source_rank": self.source_rank,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "text_snippet": self.text_snippet,
            "source_url": self.source_url,
            "classification": self.classification,
        }


class TopSourcesResolver:
    """
    Greedy Weighted Set Cover Engine for Dynamic Top Sources Attribution.
    Eliminates overlapping credit and guarantees sum(Source_Sim) <= 100%.
    """

    def __init__(self, min_continuous_words: int = 8):
        self.min_continuous_words = min_continuous_words

    def resolve(
        self,
        raw_matches: List[RawMatch],
        tokens: List[TokenSpan],
        full_text: str,
        total_words: int,
        excluded_token_indices: Optional[Set[int]] = None,
        exclusion_engine: Optional[ExclusionFiltersEngine] = None,
    ) -> Tuple[List[TopSourceItem], List[AnnotatedDocumentSpan], Set[int]]:
        """
        Executes Greedy Weighted Set-Cover across all raw candidate matches:
        Returns:
            top_sources: List of TopSourceItem objects ranked 1, 2, ...
            annotated_spans: Non-overlapping AnnotatedDocumentSpan objects with exact coordinates
            claimed_tokens: Complete set of discrete document token indices matched
        """
        excluded_set = excluded_token_indices or set()
        clf_engine = exclusion_engine or ExclusionFiltersEngine()

        # Step 1: Collect eligible tokens per source
        # Map source_id -> metadata and set of unique eligible token indices
        source_tokens_map: Dict[str, Set[int]] = {}
        source_meta_map: Dict[str, Dict[str, Any]] = {}
        source_raw_matches: Dict[str, List[RawMatch]] = {}

        for m in raw_matches:
            sid = m.source_id
            if sid not in source_tokens_map:
                source_tokens_map[sid] = set()
                source_meta_map[sid] = {
                    "source_id": sid,
                    "source_name": m.source_name,
                    "source_type": m.source_type,
                    "source_url": m.source_url,
                }
                source_raw_matches[sid] = []

            # Filter out tokens in active excluded regions (e.g. bibliography, quotes if excluded)
            eligible_match_tokens = {
                t_idx for t_idx in range(m.sub_token_start, m.sub_token_end + 1)
                if t_idx not in excluded_set
            }
            if eligible_match_tokens:
                source_tokens_map[sid].update(eligible_match_tokens)
                source_raw_matches[sid].append(m)

        # Step 2: Iterative Greedy Attribution
        claimed_tokens: Set[int] = set()
        top_sources: List[TopSourceItem] = []
        annotated_spans: List[AnnotatedDocumentSpan] = []
        span_id_counter = 1
        current_rank = 1

        active_sources = set(source_tokens_map.keys())

        while active_sources:
            best_source_id: Optional[str] = None
            best_unclaimed_tokens: Set[int] = set()
            max_unclaimed_count = -1

            # Recalculate remaining unique token counts for all remaining sources
            for sid in active_sources:
                unclaimed = source_tokens_map[sid] - claimed_tokens
                # Check continuous runs of unclaimed tokens to enforce minimum threshold
                continuous_runs = self._extract_continuous_runs(unclaimed)
                # Keep runs that satisfy minimum continuous threshold
                valid_runs = [r for r in continuous_runs if len(r) >= self.min_continuous_words]
                valid_unclaimed_count = sum(len(r) for r in valid_runs)

                if valid_unclaimed_count > max_unclaimed_count:
                    max_unclaimed_count = valid_unclaimed_count
                    best_source_id = sid
                    # Store only the tokens in valid runs
                    valid_tokens = set()
                    for r in valid_runs:
                        valid_tokens.update(r)
                    best_unclaimed_tokens = valid_tokens

            # If no source has any valid remaining unclaimed tokens, terminate iteration
            if not best_source_id or max_unclaimed_count <= 0:
                break

            # Assign best_source_id as Top Source #current_rank
            src_info = source_meta_map[best_source_id]
            matched_words = len(best_unclaimed_tokens)

            # Compute Source Similarity Percentage: (N_source / N_total) * 100
            sim_ratio = (matched_words / max(1, total_words)) * 100.0
            if sim_ratio < 1.0:
                sim_display = "<1%"
            else:
                sim_display = int(round(sim_ratio))

            top_source = TopSourceItem(
                rank=current_rank,
                source_id=best_source_id,
                source_name=src_info["source_name"],
                source_type=src_info["source_type"],
                similarity_percent=sim_display,
                matched_word_count=matched_words,
                source_url=src_info["source_url"],
                attributed_tokens=best_unclaimed_tokens
            )
            top_sources.append(top_source)

            # Mark tokens as CLAIMED
            claimed_tokens.update(best_unclaimed_tokens)
            active_sources.remove(best_source_id)

            # Generate disjoint AnnotatedDocumentSpans for continuous runs of attributed tokens
            runs = self._extract_continuous_runs(best_unclaimed_tokens)
            for run in runs:
                if not run:
                    continue
                run_start_tok = min(run)
                run_end_tok = max(run)

                if run_start_tok < len(tokens) and run_end_tok < len(tokens):
                    start_char = tokens[run_start_tok].start_char
                    end_char = tokens[run_end_tok].end_char
                    snippet = full_text[start_char:end_char].strip()

                    classification = clf_engine.classify_match_span(start_char, end_char, full_text)

                    annotated_spans.append(AnnotatedDocumentSpan(
                        span_id=span_id_counter,
                        source_rank=current_rank,
                        start_char=start_char,
                        end_char=end_char,
                        text_snippet=snippet,
                        source_url=src_info["source_url"],
                        classification=classification,
                        token_start=run_start_tok,
                        token_end=run_end_tok
                    ))
                    span_id_counter += 1

            current_rank += 1

        # Sort annotated spans in manuscript order (by start_char)
        annotated_spans.sort(key=lambda s: s.start_char)

        return top_sources, annotated_spans, claimed_tokens

    @staticmethod
    def _extract_continuous_runs(indices: Set[int]) -> List[List[int]]:
        """Groups discrete integer token indices into continuous ascending runs."""
        if not indices:
            return []
        sorted_indices = sorted(indices)
        runs: List[List[int]] = []
        current_run: List[int] = [sorted_indices[0]]

        for idx in sorted_indices[1:]:
            if idx == current_run[-1] + 1:
                current_run.append(idx)
            else:
                runs.append(current_run)
                current_run = [idx]

        if current_run:
            runs.append(current_run)

        return runs
