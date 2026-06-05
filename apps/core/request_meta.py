"""Safe request metadata helpers."""
from __future__ import annotations

import ipaddress


def _clean_ip(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("[") and "]" in value:
        value = value[1:value.index("]")]
    elif value.count(":") == 1 and "." in value:
        value = value.split(":", 1)[0]
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return ""


def client_ip_from_request(request) -> str:
    """Return a validated client IP from proxy-aware request metadata."""
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        for raw_ip in forwarded_for.split(","):
            ip = _clean_ip(raw_ip)
            if ip:
                return ip

    real_ip = _clean_ip(request.META.get("HTTP_X_REAL_IP", ""))
    if real_ip:
        return real_ip

    return _clean_ip(request.META.get("REMOTE_ADDR", ""))
