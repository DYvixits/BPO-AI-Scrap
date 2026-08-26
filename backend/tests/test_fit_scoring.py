from app.engines.fit_scoring.engine import compute_fit
from app.engines.query_intelligence.objective import ResearchObjective


def _objective(**kwargs) -> ResearchObjective:
    return ResearchObjective(**kwargs)


def test_no_criteria_returns_none_score():
    result = compute_fit(_objective(), "Acme is a great company.")
    assert result.score is None
    assert result.matched_factors == []
    assert result.unmatched_factors == []


def test_no_text_with_criteria_matches_nothing():
    result = compute_fit(_objective(industry=["fintech"]), None)
    assert result.score == 0.0
    assert result.unmatched_factors == ["industry:fintech"]


def test_industry_match():
    result = compute_fit(_objective(industry=["fintech"]), "Acme is a leading fintech startup.")
    assert result.score == 1.0
    assert result.matched_factors == ["industry:fintech"]


def test_geography_match():
    result = compute_fit(_objective(geography=["Nigeria"]), "Acme is based in Nigeria.")
    assert result.score == 1.0
    assert result.matched_factors == ["geography:Nigeria"]


def test_required_attribute_match():
    result = compute_fit(_objective(required_attributes=["ceo"]), "Our CEO leads the company.")
    assert result.score == 1.0
    assert result.matched_factors == ["required_attribute:ceo"]


def test_partial_match_across_multiple_criteria():
    objective = _objective(industry=["fintech"], geography=["Nigeria"])
    result = compute_fit(objective, "Acme is a fintech company based in Kenya.")
    assert result.score == 0.5
    assert result.matched_factors == ["industry:fintech"]
    assert result.unmatched_factors == ["geography:Nigeria"]


def test_matching_is_case_insensitive():
    result = compute_fit(_objective(industry=["fintech"]), "ACME IS A FINTECH COMPANY.")
    assert result.score == 1.0
