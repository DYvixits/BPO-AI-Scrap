from app.engines.extraction.structured import extract_structured_data


def test_extracts_single_json_ld_object():
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type": "Organization", "name": "Acme Inc", "email": "hi@acme.com"}
    </script>
    </head><body></body></html>
    """
    data = extract_structured_data(html, url="https://acme.com")
    assert data.json_ld == [{"@type": "Organization", "name": "Acme Inc", "email": "hi@acme.com"}]


def test_extracts_json_ld_array():
    html = """
    <html><head>
    <script type="application/ld+json">
    [{"@type": "Organization", "name": "Acme"}, {"@type": "WebSite", "name": "acme.com"}]
    </script>
    </head></html>
    """
    data = extract_structured_data(html, url="https://acme.com")
    assert len(data.json_ld) == 2


def test_malformed_json_ld_is_ignored_not_raised():
    html = """
    <html><head>
    <script type="application/ld+json">{not valid json</script>
    </head></html>
    """
    data = extract_structured_data(html, url="https://acme.com")
    assert data.json_ld == []


def test_extracts_meta_description_and_og_tags():
    html = """
    <html><head>
    <meta name="description" content="Acme builds things.">
    <meta property="og:title" content="Acme Inc">
    <meta property="og:description" content="We build things.">
    <meta property="og:site_name" content="Acme">
    </head></html>
    """
    data = extract_structured_data(html, url="https://acme.com")
    assert data.meta_description == "Acme builds things."
    assert data.og_title == "Acme Inc"
    assert data.og_description == "We build things."
    assert data.og_site_name == "Acme"


def test_extracts_emails_from_visible_text():
    html = "<html><body><p>Contact us at hello@acme.com or press@acme.com</p></body></html>"
    data = extract_structured_data(html, url="https://acme.com")
    assert data.emails == ["hello@acme.com", "press@acme.com"]


def test_deduplicates_repeated_emails():
    html = "<html><body><p>hello@acme.com and again hello@acme.com</p></body></html>"
    data = extract_structured_data(html, url="https://acme.com")
    assert data.emails == ["hello@acme.com"]


def test_extracts_phone_numbers():
    html = "<html><body><p>Call us: +1 415-555-0132</p></body></html>"
    data = extract_structured_data(html, url="https://acme.com")
    assert len(data.phones) == 1


def test_empty_page_yields_empty_structured_data():
    data = extract_structured_data(
        "<html><body><p>Nothing here.</p></body></html>", url="https://acme.com"
    )
    assert data.json_ld == []
    assert data.meta_description is None
    assert data.og_title is None
    assert data.emails == []
    assert data.phones == []


def test_as_dict_round_trips_all_fields():
    html = '<html><head><meta name="description" content="Test"></head></html>'
    data = extract_structured_data(html, url="https://acme.com")
    as_dict = data.as_dict()
    assert as_dict["meta_description"] == "Test"
    assert set(as_dict.keys()) == {
        "json_ld",
        "meta_description",
        "og_title",
        "og_description",
        "og_site_name",
        "emails",
        "phones",
    }
