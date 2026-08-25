from app.engines.extraction.dedup import NearDuplicateDetector, jaccard_similarity, shingles


def test_identical_text_has_similarity_one():
    text = "Acme builds fintech products for African markets and hires locally."
    assert jaccard_similarity(shingles(text), shingles(text)) == 1.0


def test_completely_different_text_has_low_similarity():
    a = "Acme builds fintech products for African markets and hires locally this year."
    b = "The weather in Antarctica is extremely cold during the winter months of June."
    assert jaccard_similarity(shingles(a), shingles(b)) < 0.1


_LONG_PASSAGE = (
    "Acme is a fintech company based in Lagos Nigeria that builds payment "
    "infrastructure for small businesses across West Africa and beyond, serving "
    "thousands of merchants daily with reliable and secure transaction processing."
)


def test_near_duplicate_text_has_high_similarity():
    # Realistic near-duplicate scenario: the same page content with a
    # session token or timestamp appended — most shingles are unchanged.
    a = _LONG_PASSAGE
    b = _LONG_PASSAGE + " Session ID: 8f3a91."
    assert jaccard_similarity(shingles(a), shingles(b)) > 0.85


def test_both_empty_is_perfectly_similar():
    assert jaccard_similarity(set(), set()) == 1.0


def test_one_empty_is_not_similar():
    assert jaccard_similarity({"a b c d e"}, set()) == 0.0


def test_short_text_below_shingle_size_still_produces_a_shingle():
    assert shingles("two words", k=5) == {"two words"}


def test_empty_text_produces_no_shingles():
    assert shingles("", k=5) == set()


def test_detector_flags_second_near_identical_page():
    detector = NearDuplicateDetector()
    first = _LONG_PASSAGE
    second = _LONG_PASSAGE + " Session ID: 8f3a91."
    assert detector.check_and_record(first) is False
    assert detector.check_and_record(second) is True


def test_detector_does_not_flag_distinct_pages():
    detector = NearDuplicateDetector()
    first = "Acme builds fintech products for African markets and hires locally this year."
    second = "The weather in Antarctica is extremely cold during the winter months of June."
    assert detector.check_and_record(first) is False
    assert detector.check_and_record(second) is False


def test_detector_handles_none_text():
    detector = NearDuplicateDetector()
    assert detector.check_and_record(None) is False
    assert detector.check_and_record(None) is False
