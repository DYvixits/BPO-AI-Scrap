import pytest

from app.engines.crawler.ssrf_guard import UnsafeURLError, assert_safe_url


def test_rejects_non_http_scheme():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("file:///etc/passwd")


def test_rejects_loopback_literal():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://127.0.0.1/admin")


def test_rejects_ipv6_loopback_literal():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://[::1]/admin")


def test_rejects_private_rfc1918_literal():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://10.0.0.5/internal")
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://192.168.1.1/internal")
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://172.16.0.1/internal")


def test_rejects_link_local_cloud_metadata_literal():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://169.254.169.254/latest/meta-data/")


def test_rejects_denylisted_hostname():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://metadata.google.internal/computeMetadata/v1/")


def test_rejects_url_with_no_hostname():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http:///no-host")


def test_allows_public_looking_url_without_resolving(monkeypatch):
    # Avoid a real DNS lookup in CI: stub resolution to a public IP and
    # confirm the guard accepts it — the actual "no live network in tests"
    # boundary, not a claim that example.com is reachable from CI.
    from app.engines.crawler import ssrf_guard

    def _fake_getaddrinfo(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(ssrf_guard.socket, "getaddrinfo", _fake_getaddrinfo)
    assert_safe_url("https://example.com/page")


def test_rejects_hostname_that_resolves_to_private_ip(monkeypatch):
    from app.engines.crawler import ssrf_guard

    def _fake_getaddrinfo(host, port):
        return [(2, 1, 6, "", ("10.0.0.1", 0))]

    monkeypatch.setattr(ssrf_guard.socket, "getaddrinfo", _fake_getaddrinfo)
    with pytest.raises(UnsafeURLError):
        assert_safe_url("https://looks-public-but-isnt.example/")
