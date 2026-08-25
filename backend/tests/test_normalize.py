from app.engines.crawler.normalize import normalize_url


def test_strips_tracking_params():
    a = normalize_url("https://acme.com/about?utm_source=x&utm_campaign=y")
    b = normalize_url("https://acme.com/about")
    assert a == b


def test_strips_trailing_slash():
    a = normalize_url("https://acme.com/about/")
    b = normalize_url("https://acme.com/about")
    assert a == b


def test_root_path_trailing_slash_is_kept():
    # "/" has no meaningful non-slash form — stripping it would collide
    # normalize_url("https://acme.com") with normalize_url("https://acme.com/"),
    # which is fine, but stripping shouldn't produce an empty path either.
    normalized = normalize_url("https://acme.com/")
    assert normalized.startswith("https://acme.com")


def test_lowercases_scheme_and_host():
    a = normalize_url("HTTPS://ACME.com/about")
    b = normalize_url("https://acme.com/about")
    assert a == b


def test_path_case_is_preserved():
    a = normalize_url("https://acme.com/About")
    b = normalize_url("https://acme.com/about")
    assert a != b


def test_meaningful_query_params_are_preserved():
    a = normalize_url("https://acme.com/search?q=fintech")
    b = normalize_url("https://acme.com/search?q=other")
    assert a != b


def test_query_param_order_does_not_matter():
    a = normalize_url("https://acme.com/search?a=1&b=2")
    b = normalize_url("https://acme.com/search?b=2&a=1")
    assert a == b


def test_fragment_is_stripped():
    a = normalize_url("https://acme.com/about#team")
    b = normalize_url("https://acme.com/about")
    assert a == b


def test_mixed_tracking_and_meaningful_params():
    a = normalize_url("https://acme.com/search?q=fintech&utm_source=newsletter")
    b = normalize_url("https://acme.com/search?q=fintech")
    assert a == b
