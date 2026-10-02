"""Saved search name helpers."""

from __future__ import annotations

import os
import re

INVALID_NAME_RE = re.compile(r'[\\/:*?"<>|\[\]]+')


def search_name_from_path(path: str) -> str:
    base = os.path.basename(path.replace("\\", "/"))
    if base.lower().endswith(".md"):
        base = base[:-3]
    return sanitize_search_name(base)


def sanitize_search_name(name: str) -> str:
    cleaned = INVALID_NAME_RE.sub("_", (name or "").strip())
    cleaned = cleaned.strip(" .")
    return cleaned or "unnamed_search"


def posix_relpath(path: str, start: str) -> str:
    relative = os.path.relpath(path, start)
    return relative.replace("\\", "/")
