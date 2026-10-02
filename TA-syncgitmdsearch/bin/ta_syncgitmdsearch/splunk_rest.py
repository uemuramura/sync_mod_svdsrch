"""Minimal Splunk REST helpers used only inside Splunk."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote


class SplunkRestError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def request(
    path: str,
    session_key: str,
    method: str = "GET",
    postargs: Optional[Dict[str, Any]] = None,
    getargs: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Any]:
    from splunk.rest import simpleRequest

    kwargs = {
        "sessionKey": session_key,
        "method": method,
        "raiseAllErrors": False,
    }
    if postargs is not None:
        kwargs["postargs"] = postargs
    if getargs is not None:
        kwargs["getargs"] = getargs
    response, content = simpleRequest(path, **kwargs)
    status = int(response.get("status", 0))
    body = content.decode("utf-8") if isinstance(content, bytes) else (content or "")
    parsed = None
    if body:
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = body
    if status >= 400:
        raise SplunkRestError(_error_message(parsed, body, status), status=status)
    return status, parsed


def encode_segment(value: str) -> str:
    return quote(value, safe="")


def _error_message(parsed: Any, raw: str, status: int) -> str:
    if isinstance(parsed, dict):
        messages = parsed.get("messages") or []
        if messages:
            first = messages[0]
            if isinstance(first, dict) and first.get("text"):
                return str(first["text"])
    if isinstance(raw, str) and raw.strip():
        return raw.strip()[:500]
    return "Splunk REST request failed with status {}".format(status)
