from app.engines.crawler.prioritization import InformationGainTracker, score_candidate
from app.engines.query_intelligence.objective import ResearchObjective


def _objective(**overrides) -> ResearchObjective:
    base = dict(
        target_entities=["company"],
        geography=[],
        industry=[],
        company_size_min=None,
        company_size_max=None,
        required_attributes=[],
        signals=[],
        freshness="any",
        matched_keywords={},
    )
    base.update(overrides)
    return ResearchObjective(**base)


def test_page_matching_required_attribute_signal_scores_higher():
    objective = _objective(required_attributes=["ceo"])
    about_score = score_candidate(
        url="https://acme.com/about", anchor_text="About us", objective=objective, depth=0
    )
    pricing_score = score_candidate(
        url="https://acme.com/pricing", anchor_text="Pricing", objective=objective, depth=0
    )
    assert about_score > pricing_score


def test_no_required_attributes_gives_flat_base_score():
    objective = _objective(required_attributes=[])
    a = score_candidate(url="https://acme.com/about", anchor_text="", objective=objective, depth=0)
    b = score_candidate(url="https://acme.com/x", anchor_text="", objective=objective, depth=0)
    assert a == b


def test_depth_decays_score():
    objective = _objective(required_attributes=["ceo"])
    shallow = score_candidate(
        url="https://acme.com/about", anchor_text="", objective=objective, depth=0
    )
    deep = score_candidate(
        url="https://acme.com/about", anchor_text="", objective=objective, depth=3
    )
    assert deep < shallow


def test_anchor_text_alone_can_trigger_a_signal_match():
    objective = _objective(required_attributes=["ceo"])
    # URL gives no hint, but the anchor text does.
    scored = score_candidate(
        url="https://acme.com/p123", anchor_text="Our Leadership", objective=objective, depth=0
    )
    unscored = score_candidate(
        url="https://acme.com/p123", anchor_text="Random Link", objective=objective, depth=0
    )
    assert scored > unscored


def test_gain_tracker_disabled_when_no_required_attributes():
    tracker = InformationGainTracker([])
    assert tracker.enabled is False
    assert tracker.record_page("CEO John Smith, revenue $10M") == 0
    assert tracker.all_satisfied is False


def test_gain_tracker_records_new_attributes_found_in_text():
    tracker = InformationGainTracker(["ceo", "revenue"])
    assert tracker.enabled is True
    gained = tracker.record_page("Our CEO is Jane Doe. Revenue grew 20% this year.")
    assert gained == 2
    assert tracker.satisfied == {"ceo", "revenue"}
    assert tracker.all_satisfied is True


def test_gain_tracker_does_not_recount_already_satisfied_attributes():
    tracker = InformationGainTracker(["ceo"])
    assert tracker.record_page("Our CEO is Jane Doe.") == 1
    assert tracker.record_page("The CEO spoke at a conference.") == 0


def test_gain_tracker_handles_none_text():
    tracker = InformationGainTracker(["ceo"])
    assert tracker.record_page(None) == 0


def test_gain_tracker_partial_satisfaction_not_all_satisfied():
    tracker = InformationGainTracker(["ceo", "revenue"])
    tracker.record_page("Our CEO is Jane Doe.")
    assert tracker.all_satisfied is False
