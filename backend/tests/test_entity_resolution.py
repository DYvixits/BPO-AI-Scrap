from app.engines.entity_resolution.resolver import (
    ResolvablePage,
    normalize_company_name,
    resolve_companies,
)


def _page(url, domain, title=None, **structured) -> ResolvablePage:
    return ResolvablePage(url=url, domain=domain, title=title, structured_data=structured)


def test_normalize_strips_legal_suffixes_and_punctuation():
    assert normalize_company_name("Acme, Inc.") == "acme"
    assert normalize_company_name("ACME Incorporated") == "acme"
    assert normalize_company_name("Acme Group") == "acme"


def test_empty_pages_returns_no_companies():
    assert resolve_companies([]) == []


def test_single_domain_pages_group_into_one_company_with_full_confidence():
    pages = [
        _page("https://acme.com/", "acme.com", title="Acme"),
        _page("https://acme.com/about", "acme.com", title="About Acme"),
    ]
    companies = resolve_companies(pages)
    assert len(companies) == 1
    assert companies[0].match_confidence == 1.0
    assert set(companies[0].member_urls) == {"https://acme.com/", "https://acme.com/about"}


def test_different_domains_with_different_names_stay_separate():
    pages = [
        _page("https://acme.com/", "acme.com", og_site_name="Acme"),
        _page("https://other.com/", "other.com", og_site_name="Other Co"),
    ]
    companies = resolve_companies(pages)
    assert len(companies) == 2


def test_different_domains_with_matching_names_merge_with_lower_confidence():
    pages = [
        _page("https://acme.com/", "acme.com", og_site_name="Acme Inc"),
        _page(
            "https://crunchbase.com/organization/acme",
            "crunchbase.com",
            og_site_name="ACME Incorporated",
        ),
    ]
    companies = resolve_companies(pages)
    assert len(companies) == 1
    assert companies[0].match_confidence == 0.7
    assert len(companies[0].member_urls) == 2


def test_json_ld_organization_name_takes_priority_over_og_site_name():
    pages = [
        _page(
            "https://acme.com/",
            "acme.com",
            og_site_name="Wrong Name",
            json_ld=[{"@type": "Organization", "name": "Acme Real Name"}],
        )
    ]
    companies = resolve_companies(pages)
    assert companies[0].canonical_name == "Acme Real Name"


def test_og_title_separator_is_split_on():
    pages = [_page("https://acme.com/", "acme.com", og_title="Acme - Home of great products")]
    companies = resolve_companies(pages)
    assert companies[0].canonical_name == "Acme"


def test_falls_back_to_domain_derived_name_when_nothing_else_available():
    pages = [_page("https://acme-labs.com/", "acme-labs.com")]
    companies = resolve_companies(pages)
    assert companies[0].canonical_name == "Acme Labs"


def test_www_prefix_does_not_create_a_separate_domain_group():
    pages = [
        _page("https://acme.com/", "acme.com", og_site_name="Acme"),
        _page("https://www.acme.com/about", "www.acme.com", og_site_name="Acme"),
    ]
    companies = resolve_companies(pages)
    assert len(companies) == 1
    assert len(companies[0].member_urls) == 2


def test_description_is_taken_from_first_page_that_has_one():
    pages = [
        _page("https://acme.com/", "acme.com", og_site_name="Acme"),
        _page(
            "https://acme.com/about",
            "acme.com",
            og_site_name="Acme",
            meta_description="We build things.",
        ),
    ]
    companies = resolve_companies(pages)
    assert companies[0].description == "We build things."


def test_aliases_record_every_distinct_name_and_the_domain():
    # "Acme" and "Acme Inc" normalize to the same string (legal-suffix
    # stripping), so only the first literal form is kept as an alias —
    # use two names that are genuinely different after normalization to
    # prove distinct name variants both get recorded.
    pages = [
        _page("https://acme.com/", "acme.com", og_site_name="Acme"),
        _page("https://acme.com/about", "acme.com", og_site_name="Acme Technologies"),
    ]
    companies = resolve_companies(pages)
    alias_values = {a.value for a in companies[0].aliases}
    assert "Acme" in alias_values
    assert "Acme Technologies" in alias_values
    assert "acme.com" in alias_values


def test_pages_with_no_domain_are_skipped():
    pages = [_page("not-a-url", "")]
    assert resolve_companies(pages) == []
