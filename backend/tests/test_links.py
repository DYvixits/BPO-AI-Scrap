from app.engines.crawler.links import extract_links


def test_resolves_relative_links_against_base_url():
    html = '<a href="/about">About</a><a href="team/">Team</a>'
    links = extract_links(html, base_url="https://acme.com/home")
    urls = {link.url for link in links}
    assert "https://acme.com/about" in urls
    assert "https://acme.com/team/" in urls


def test_captures_anchor_text():
    html = '<a href="/about">  About Us  </a>'
    links = extract_links(html, base_url="https://acme.com")
    assert links[0].anchor_text == "About Us"


def test_filters_out_cross_domain_links():
    html = '<a href="https://acme.com/about">Ours</a><a href="https://other.com/page">Theirs</a>'
    links = extract_links(html, base_url="https://acme.com")
    urls = {link.url for link in links}
    assert urls == {"https://acme.com/about"}


def test_www_prefix_counts_as_same_domain():
    html = '<a href="https://www.acme.com/about">About</a>'
    links = extract_links(html, base_url="https://acme.com")
    assert len(links) == 1


def test_skips_non_http_schemes():
    html = (
        '<a href="mailto:hi@acme.com">Email</a>'
        '<a href="tel:+123456">Call</a>'
        '<a href="javascript:void(0)">JS</a>'
    )
    links = extract_links(html, base_url="https://acme.com")
    assert links == []


def test_skips_asset_extensions():
    html = '<a href="/brochure.pdf">PDF</a><a href="/logo.png">Logo</a>'
    links = extract_links(html, base_url="https://acme.com")
    assert links == []


def test_skips_fragment_only_links():
    html = '<a href="#section">Jump</a>'
    links = extract_links(html, base_url="https://acme.com")
    assert links == []


def test_dedupes_same_url_with_different_fragments():
    html = '<a href="/about#team">Team</a><a href="/about#history">History</a>'
    links = extract_links(html, base_url="https://acme.com")
    assert len(links) == 1
    assert links[0].url == "https://acme.com/about"


def test_no_links_returns_empty_list():
    assert extract_links("<p>No links here</p>", base_url="https://acme.com") == []
