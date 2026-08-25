from app.engines.query_intelligence.parser import parse_query, parse_result_limit


def test_parses_geography_and_industry():
    obj = parse_query("Find fintech companies in Cameroon with recent hiring signals")
    assert obj.industry == ["fintech"]
    assert obj.geography == ["Cameroon"]
    assert obj.signals == ["hiring"]
    assert obj.freshness == "recent"
    assert obj.target_entities == ["company"]


def test_matched_keywords_records_literal_matches():
    obj = parse_query("Cameroonian fintech companies")
    assert "cameroonian" in obj.matched_keywords["geography"]
    assert "fintech" in obj.matched_keywords["industry"]


def test_detects_person_target_entities():
    obj = parse_query("Find CISOs and decision makers at healthcare companies in Kenya")
    assert "person" in obj.target_entities
    assert obj.industry == ["healthcare"]
    assert obj.geography == ["Kenya"]


def test_detects_multiple_signals():
    obj = parse_query("Companies that are hiring and recently raised funding")
    assert set(obj.signals) == {"hiring", "funding"}


def test_detects_negative_signal():
    obj = parse_query("Companies with recent layoffs")
    assert obj.signals == ["layoffs"]


def test_company_size_plus_pattern():
    obj = parse_query("Companies with 50+ employees")
    assert obj.company_size_min == 50
    assert obj.company_size_max is None


def test_company_size_range_pattern():
    obj = parse_query("Companies with 50-200 employees")
    assert obj.company_size_min == 50
    assert obj.company_size_max == 200


def test_company_size_more_than_pattern():
    obj = parse_query("Companies with more than 100 employees")
    assert obj.company_size_min == 100


def test_required_attributes_detected():
    obj = parse_query("Find companies and their CEO, revenue, and founding year")
    assert "ceo" in obj.required_attributes
    assert "revenue" in obj.required_attributes
    assert "founded_year" in obj.required_attributes


def test_no_matches_leaves_defaults():
    obj = parse_query("asdf qwerty")
    assert obj.geography == []
    assert obj.industry == []
    assert obj.signals == []
    assert obj.target_entities == ["company"]
    assert obj.matched_keywords == {}


def test_parse_result_limit():
    assert parse_result_limit("Find 500 companies in the fintech sector") == 500
    assert parse_result_limit("Find fintech companies") is None


def test_parse_result_limit_with_adjective_between_number_and_noun():
    # Caught live against the running app: a bare "\d+\s+companies" pattern
    # missed this extremely common phrasing entirely.
    assert parse_result_limit("Find 250 fintech companies in Cameroon") == 250
    assert parse_result_limit("Find 250 Cameroonian fintech companies") == 250


def test_parse_result_limit_does_not_match_across_distant_words():
    assert parse_result_limit("250 people work at these growing companies") is None
