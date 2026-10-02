"""Create or update Splunk saved searches from extracted SPL."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ta_syncgitmdsearch.constants import (
    ALLOWED_SAVEDSEARCH_KEYS,
    BOOLEAN_SAVEDSEARCH_KEYS,
    SOURCE_MARKER_PREFIX,
    SOURCE_MARKER_SUFFIX,
)
from ta_syncgitmdsearch.splunk_rest import SplunkRestError, encode_segment, request


def source_marker(relpath: str) -> str:
    return "{}{}{}".format(SOURCE_MARKER_PREFIX, relpath, SOURCE_MARKER_SUFFIX)


def build_description(metadata: Dict[str, Any], relpath: str) -> str:
    marker = source_marker(relpath)
    description = str(metadata.get("description") or "").strip()
    if description:
        return description + "\n\n" + marker
    return marker


def is_managed(description: Optional[str]) -> bool:
    return SOURCE_MARKER_PREFIX in (description or "")


def upsert_savedsearch(
    session_key: str,
    target_app: str,
    target_owner: str,
    name: str,
    spl: str,
    metadata: Dict[str, Any],
    relpath: str,
    overwrite: bool,
) -> str:
    payload = _savedsearch_payload(spl, metadata, relpath)
    existing = _get_savedsearch(session_key, target_app, target_owner, name)
    if existing is None:
        create_args = dict(payload)
        create_args["name"] = name
        request(
            "/servicesNS/{}/{}/saved/searches".format(target_owner, target_app),
            session_key,
            method="POST",
            postargs=create_args,
        )
        return "created"
    if not overwrite and not is_managed(existing.get("description")):
        return "skipped_exists"
    request(
        "/servicesNS/{}/{}/saved/searches/{}".format(
            target_owner, target_app, encode_segment(name)
        ),
        session_key,
        method="POST",
        postargs=payload,
    )
    return "updated"


def _get_savedsearch(
    session_key: str, target_app: str, target_owner: str, name: str
) -> Optional[Dict[str, Any]]:
    path = "/servicesNS/{}/{}/saved/searches/{}".format(
        target_owner, target_app, encode_segment(name)
    )
    try:
        _, payload = request(path, session_key, getargs={"output_mode": "json"})
    except SplunkRestError as exc:
        if exc.status == 404:
            return None
        raise
    entries = payload.get("entry") if isinstance(payload, dict) else None
    if not entries:
        return None
    return entries[0].get("content") or {}


def _savedsearch_payload(spl: str, metadata: Dict[str, Any], relpath: str) -> Dict[str, str]:
    payload = {
        "search": spl,
        "description": build_description(metadata, relpath),
    }
    for key, value in metadata.items():
        if key not in ALLOWED_SAVEDSEARCH_KEYS or key == "description":
            continue
        payload[key] = _stringify(key, value)
    return payload


def _stringify(key: str, value: Any) -> str:
    if key in BOOLEAN_SAVEDSEARCH_KEYS:
        if isinstance(value, bool):
            return "1" if value else "0"
        text = str(value).strip().lower()
        return "1" if text in ("1", "true", "yes", "on") else "0"
    return str(value)
