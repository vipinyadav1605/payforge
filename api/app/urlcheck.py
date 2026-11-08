import ipaddress
import socket
from urllib.parse import urlparse

from .errors import ApiError


def validate_webhook_url(url: str, env: str) -> None:
    """SSRF guard: in prod only public https URLs are allowed, so a merchant can't make
    PayForge call internal services (metadata endpoints, databases, localhost...)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ApiError(422, "invalid_webhook_url", "Webhook URL must be a valid http(s) URL.")
    if env != "prod":
        return
    if parsed.scheme != "https":
        raise ApiError(422, "invalid_webhook_url", "Webhook URL must use https in production.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    except socket.gaierror as exc:
        raise ApiError(422, "invalid_webhook_url", "Webhook host does not resolve.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ApiError(422, "invalid_webhook_url", "Webhook URL points to a non-public address.")
