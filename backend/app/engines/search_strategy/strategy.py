"""Search Strategy Engine (master spec §5): a single literal query is never
treated as sufficient. Given a ResearchObjective, generate a small set of
complementary queries that cover different angles (base discovery, per
signal, decision-maker discovery) instead of relying on the user's exact
wording alone.

Deliberately capped at MAX_QUERIES: more queries costs more crawl budget
for diminishing returns, and every query generated here eventually becomes
real HTTP requests — this is not a place to be generous by default (master
spec §67: optimize for useful information per cost, not query count).
"""

from app.engines.query_intelligence.objective import ResearchObjective

MAX_QUERIES = 4


def build_queries(original_query: str, objective: ResearchObjective) -> list[str]:
    queries: list[str] = [original_query]

    industry = objective.industry[0] if objective.industry else None
    geography = objective.geography[0] if objective.geography else None

    if industry and geography:
        queries.append(f"{industry} companies in {geography}")
    elif industry:
        queries.append(f"{industry} companies")
    elif geography:
        queries.append(f"companies in {geography}")

    for signal in objective.signals:
        if len(queries) >= MAX_QUERIES:
            break
        signal_phrase = signal.replace("_", " ")
        scope = " ".join(filter(None, [industry, geography]))
        query = f"{scope} {signal_phrase}".strip() if scope else f"{signal_phrase} companies"
        queries.append(query)

    if "person" in objective.target_entities and len(queries) < MAX_QUERIES:
        scope = " ".join(filter(None, [industry, geography]))
        queries.append(
            f"{scope} decision makers executives".strip() if scope else "company decision makers"
        )

    # Dedupe while preserving order (two branches above can coincidentally
    # produce the same string, e.g. no industry/geography matched at all).
    seen: set[str] = set()
    deduped: list[str] = []
    for q in queries:
        normalized = q.strip()
        if normalized and normalized.lower() not in seen:
            seen.add(normalized.lower())
            deduped.append(normalized)

    return deduped[:MAX_QUERIES]
