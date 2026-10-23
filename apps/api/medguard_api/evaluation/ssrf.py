"""Outbound-call guard. The evaluation worker calls user-supplied URLs, so it must not be usable to reach
internal services (cloud metadata, Valkey, Postgres, Keycloak...)."""
import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


class BlockedTarget(Exception):
    pass


def _check_ip(ip: str, allow_private: bool) -> None:
    addr = ipaddress.ip_address(ip)
    # 169.254.0.0/16 (cloud metadata) and unspecified/multicast stay blocked even when private targets are allowed.
    # Checked before is_global: some multicast ranges report is_global=True.
    if addr.is_link_local or addr.is_unspecified or addr.is_multicast or addr.is_reserved:
        raise BlockedTarget(f"destination {ip} is not allowed")
    if addr.is_global:
        return
    if not allow_private:
        raise BlockedTarget(f"destination {ip} is a private or loopback address; internal targets are disabled")


async def resolve_safe(url: str, allow_private: bool) -> tuple[str, str]:
    """Returns (host, ip) for a vetted URL. The caller must connect to the returned IP, not re-resolve,
    otherwise DNS rebinding could swap in an internal address after the check."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise BlockedTarget("only absolute http(s) URLs are allowed")
    port = u.port or (443 if u.scheme == "https" else 80)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(u.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise BlockedTarget(f"cannot resolve {u.hostname}") from e
    ips = sorted({i[4][0] for i in infos})
    if not ips:
        raise BlockedTarget(f"cannot resolve {u.hostname}")
    for ip in ips:  # every resolved address must be acceptable
        _check_ip(ip, allow_private)
    return u.hostname, ips[0]
