"""Deterministic local retrieval for Project WINGMAN.

The first WINGMAN experiment intentionally avoids an embeddings dependency.
TruePanel's operator manuals are small enough that a bounded lexical ranker is
sufficient to prove the grounding contract before model quality is introduced.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

from .contracts import GroundingSource

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9._/-]*", re.IGNORECASE)


def _tokens(value: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(value)]


def rank_sources(
    query: str,
    sources: Iterable[GroundingSource],
    *,
    limit: int = 6,
) -> tuple[GroundingSource, ...]:
    """Return a stable, bounded lexical ranking for sanitized sources.

    Titles are weighted more heavily than body text. Rare query terms receive
    a small inverse-document-frequency boost. Ties are resolved by source ID so
    HoloDeck and unit tests remain deterministic.
    """

    if limit <= 0:
        return ()

    materialized = tuple(sources)
    query_terms = _tokens(query)
    if not materialized or not query_terms:
        return ()

    document_terms = [
        set(_tokens(f"{source.title} {source.content}")) for source in materialized
    ]
    frequencies = Counter(
        term
        for terms in document_terms
        for term in set(query_terms).intersection(terms)
    )
    document_count = len(materialized)

    def score(source: GroundingSource, terms: set[str]) -> float:
        title_terms = Counter(_tokens(source.title))
        body_terms = Counter(_tokens(source.content))
        total = 0.0
        for term in query_terms:
            if term not in terms:
                continue
            idf = math.log((document_count + 1) / (frequencies[term] + 1)) + 1.0
            title_weight = min(title_terms[term], 2) * 3.0
            body_weight = min(body_terms[term], 4) * 1.0
            total += (title_weight + body_weight) * idf
        return total

    ranked = [
        (score(source, terms), source.source_id, source)
        for source, terms in zip(materialized, document_terms, strict=True)
    ]
    ranked = [item for item in ranked if item[0] > 0]
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return tuple(item[2] for item in ranked[:limit])


__all__ = ["rank_sources"]
