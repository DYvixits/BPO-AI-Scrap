"""SSRF protection for the crawler (SECURITY.md §"SSRF protection").

Every URL the crawler is about to request — including each redirect hop —
must pass `assert_safe_url` first. This resolves the hostname and rejects
anything that lands in a private/loopback/link-local/reserved range, which
stops naive SSRF ("crawl http://169.254.169.254/") and redirect-based SSRF
(a first-party URL that 302s to an internal address — each hop is
re-validated in `fetcher.py` before it is followed).

Known residual gap, honestly documented rather than silently accepted: this
checks the hostname's resolution at validation time but does not pin the
TCP connection to that resolved IP, so a narrow-window DNS-rebinding attack
(the name resolves safely here, then resolves to an internal address a
moment later when httpx itself connects) is not fully closed. Closing that
gap requires a custom transport that connects to the pre-validated IP
directly; tracked as a Phase 4/11 hardening item, not silently assumed done.
"""

import ipaddress
import socket
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}

# Defense in depth beyond the ip_address(...).is_* checks below: known cloud
# metadata hostnames that could otherwise resolve to a "public-looking" but
# still-sensitive address in some environments.
_DENYLISTED_HOSTNAMES = {
    "metadata.google.internal",
    "metadata.internal",
}


class UnsafeURLError(ValueError):
    pass


def _is_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (ip.version == 6 and ip.is_site_local)
    )


def resolve_and_validate(hostname: str) -> list[str]:
    """Resolve `hostname` and return its IPs, raising UnsafeURLError if any
    resolved address (or the hostname itself) is not safe to connect to."""
    if hostname.lower() in _DENYLISTED_HOSTNAMES:
        raise UnsafeURLError(f"Hostname is denylisted: {hostname}")

    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve hostname: {hostname}") from exc

    resolved_ips: list[str] = []
    for _family, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if _is_unsafe_ip(ip):
            raise UnsafeURLError(f"{hostname} resolves to a disallowed address: {ip_str}")
        resolved_ips.append(ip_str)

    if not resolved_ips:
        raise UnsafeURLError(f"No usable addresses for hostname: {hostname}")
    return resolved_ips


def assert_safe_url(url: str) -> None:
    """Raise UnsafeURLError unless `url` is a public http(s) URL."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f"Disallowed URL scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise UnsafeURLError("URL has no hostname")

    # Reject raw IP literals pointing at unsafe ranges directly (no DNS hop
    # to hide behind), then resolve hostnames through the same check.
    try:
        literal_ip = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if _is_unsafe_ip(literal_ip):
            raise UnsafeURLError(f"Disallowed literal IP address: {parsed.hostname}")
        return

    resolve_and_validate(parsed.hostname)
