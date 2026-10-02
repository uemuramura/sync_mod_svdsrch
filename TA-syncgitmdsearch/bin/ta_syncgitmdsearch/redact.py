"""Redact secrets from logs and subprocess output."""

from __future__ import annotations

import re
from typing import Iterable

URL_CREDS_RE = re.compile(r"(https?://)([^/@:]+):([^@]+)@", re.IGNORECASE)


def redact_text(message: str, secrets: Iterable[str] = ()) -> str:
    text = message or ""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return URL_CREDS_RE.sub(r"\1***:***@", text)
