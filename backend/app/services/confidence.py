"""Phase 1-3 confidence score.

This is a deliberately simple, disclosed heuristic — NOT the multi-source
Truth Engine described in the master spec (that's Phase 6). It must never be
presented to the user as "verified." The API/UI label this "basic relevance
score" so nobody mistakes it for real cross-source verification (master spec
§98: never claim "Verified" or a confidence score without having actually
computed one — this function is what actually gets computed, and the label
says exactly that much and no more).
"""

MIN_TEXT_LENGTH_FOR_SIGNAL = 400


def basic_relevance_score(*, http_status: int | None, extracted_text: str | None) -> float:
    score = 0.5  # base: the page was discovered and deemed worth crawling
    if http_status == 200:
        score += 0.3
    if extracted_text and len(extracted_text) >= MIN_TEXT_LENGTH_FOR_SIGNAL:
        score += 0.2
    return round(min(score, 1.0), 2)
