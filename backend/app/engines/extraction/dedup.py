"""Near-duplicate content detection — the third dedup layer (after crawl-
time URL normalization and exact content-hash matching) in AUDIT_BPO_CRM.md's
Phase 4. Exact-hash dedup only catches byte-identical pages; two pages that
differ by a timestamp, a session token embedded in the HTML, or a "printer-
friendly" wrapper are common on real sites and would otherwise both turn
into separate ResearchResult rows for what is, for research purposes, the
same content.

Shingling + Jaccard similarity is a standard, well-understood near-
duplicate technique (no external dependency, no ML model, easy to reason
about and test) — not a fabricated "AI similarity score": the number it
produces is exactly what it says, the fraction of shared k-word sequences.
"""

import re

_SHINGLE_SIZE = 5
_SIMILARITY_THRESHOLD = 0.9
_WORD_RE = re.compile(r"\w+")


def shingles(text: str, *, k: int = _SHINGLE_SIZE) -> set[str]:
    """Set of overlapping k-word sequences ("shingles"). Order-sensitive
    (unlike a bag-of-words), so it distinguishes real near-duplicates from
    two pages that merely share vocabulary."""
    words = _WORD_RE.findall(text.lower())
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


class NearDuplicateDetector:
    """Tracks the shingle sets of every page seen so far *within one
    research job* (a fresh instance per job — this is not a cross-job or
    cross-tenant cache) and flags a new page as a near-duplicate once its
    similarity to any previously-seen page crosses `_SIMILARITY_THRESHOLD`.
    """

    def __init__(self) -> None:
        self._seen: list[set[str]] = []

    def check_and_record(self, text: str | None) -> bool:
        """Returns True if `text` is a near-duplicate of a page already
        recorded. Records `text`'s shingles regardless, so later pages are
        compared against it too."""
        page_shingles = shingles(text) if text else set()
        is_near_duplicate = any(
            jaccard_similarity(page_shingles, seen) >= _SIMILARITY_THRESHOLD
            for seen in self._seen
            if page_shingles
        )
        self._seen.append(page_shingles)
        return is_near_duplicate
