"""Git URL validation. Credentials must never appear in the URL."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

SCP_RE = re.compile(
    r"^(?:(?P<user>[A-Za-z0-9._-]+)@)?(?P<host>[A-Za-z0-9.-]+):(?P<path>[^:\s]+)$"
)
HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")
METADATA_NETWORKS = (
    ipaddress.ip_network("169.254.169.254/32"),
    ipaddress.ip_network("fd00:ec2::254/128"),
)
BLOCKED_HOSTS = frozenset({"metadata.google.internal", "metadata.google.internal."})


def validate_git_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("repo_url is required")
    cleaned = url.strip()
    if any(char in cleaned for char in ("\n", "\r", "\x00", " ", "\\")):
        raise ValueError("repo_url contains invalid characters")
    if "://" in cleaned:
        parsed = urlparse(cleaned)
        scheme = (parsed.scheme or "").lower()
        if scheme not in ("https", "ssh"):
            raise ValueError("repo_url must use https:// or ssh://")
        if parsed.username or parsed.password:
            raise ValueError(
                "Do not embed credentials in repo_url; store them in the add-on setup page"
            )
        host = parsed.hostname
        if not host:
            raise ValueError("repo_url host is missing")
        _reject_unsafe_host(host)
        if not parsed.path or parsed.path == "/":
            raise ValueError("repo_url path is missing")
        return cleaned
    match = SCP_RE.match(cleaned)
    if match:
        _reject_unsafe_host(match.group("host"))
        path = match.group("path")
        if not path or path in (".", ".."):
            raise ValueError("repo_url path is invalid")
        return cleaned
    raise ValueError("Unsupported git URL format")


def _reject_unsafe_host(host: str) -> None:
    lowered = host.strip("[]").rstrip(".").lower()
    if not HOST_RE.match(lowered) and not _is_ip(lowered):
        raise ValueError("repo_url host is invalid")
    if lowered in BLOCKED_HOSTS:
        raise ValueError("repo_url host is not allowed")
    try:
        addrinfo = socket.getaddrinfo(lowered, None)
    except socket.gaierror:
        return
    for item in addrinfo:
        ip = ipaddress.ip_address(item[4][0])
        for network in METADATA_NETWORKS:
            if ip in network:
                raise ValueError("repo_url host is not allowed")


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False
