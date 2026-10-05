"""HTTPS Git URL validation. Credentials must never appear in the URL."""

from __future__ import annotations

import ipaddress
import re
import socket
from typing import List, Tuple
from urllib.parse import urlparse

HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")
METADATA_NETWORKS = (
    ipaddress.ip_network("169.254.169.254/32"),
    ipaddress.ip_network("fd00:ec2::254/128"),
)
BLOCKED_HOSTS = frozenset({"metadata.google.internal", "metadata.google.internal."})
TREE_MARKERS = frozenset({"tree", "blob", "src", "raw", "-"})


def validate_git_url(url: str) -> str:
    return validate_https_url(url, "repo_url")


def validate_https_url(url: str, field: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("{} is required".format(field))
    cleaned = url.strip()
    if any(char in cleaned for char in ("\n", "\r", "\x00", " ", "\\")):
        raise ValueError("{} contains invalid characters".format(field))
    parsed = urlparse(cleaned)
    if (parsed.scheme or "").lower() != "https":
        raise ValueError("{} must use https://".format(field))
    if parsed.username or parsed.password:
        raise ValueError(
            "Do not embed credentials in {}; store them in the add-on setup page".format(field)
        )
    host = parsed.hostname
    if not host:
        raise ValueError("{} host is missing".format(field))
    _reject_unsafe_host(host)
    if parsed.port not in (None, 443):
        raise ValueError("{} must use HTTPS port 443".format(field))
    return cleaned.rstrip("/")


def parse_https_repo(url: str) -> Tuple[str, List[str]]:
    parsed = urlparse(validate_https_url(url, "repo_url"))
    parts = [item for item in parsed.path.split("/") if item]
    if parts and parts[-1].endswith(".git"):
        parts[-1] = parts[-1][:-4]
    trimmed = []
    for item in parts:
        if item.lower() in TREE_MARKERS:
            break
        trimmed.append(item)
    if len(trimmed) < 2:
        raise ValueError("repo_url must include owner/group and repository name")
    return parsed.hostname or "", trimmed


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
