from app.engines.query_intelligence.objective import ResearchObjective
from app.engines.search_strategy.strategy import MAX_QUERIES, build_queries


def test_always_includes_original_query():
    objective = ResearchObjective()
    queries = build_queries("some original text", objective)
    assert queries[0] == "some original text"


def test_adds_industry_and_geography_query():
    objective = ResearchObjective(industry=["fintech"], geography=["Cameroon"])
    queries = build_queries("Find fintech companies in Cameroon", objective)
    assert "fintech companies in Cameroon" in queries


def test_adds_a_query_per_signal():
    objective = ResearchObjective(
        industry=["fintech"], geography=["Kenya"], signals=["hiring", "funding"]
    )
    queries = build_queries("original", objective)
    assert any("hiring" in q for q in queries)
    assert any("funding" in q for q in queries)


def test_adds_decision_maker_query_for_person_targets():
    objective = ResearchObjective(target_entities=["company", "person"], industry=["healthcare"])
    queries = build_queries("original", objective)
    assert any("decision makers" in q for q in queries)


def test_never_exceeds_max_queries():
    objective = ResearchObjective(
        industry=["fintech"],
        geography=["Cameroon"],
        signals=["hiring", "funding", "acquisition", "layoffs", "expansion"],
        target_entities=["company", "person"],
    )
    queries = build_queries("original", objective)
    assert len(queries) <= MAX_QUERIES


def test_deduplicates_case_insensitively():
    objective = ResearchObjective(industry=["fintech"])
    queries = build_queries("fintech companies", objective)
    normalized = [q.lower() for q in queries]
    assert len(normalized) == len(set(normalized))


def test_empty_objective_returns_only_original_query():
    objective = ResearchObjective()
    queries = build_queries("just a plain query", objective)
    assert queries == ["just a plain query"]
