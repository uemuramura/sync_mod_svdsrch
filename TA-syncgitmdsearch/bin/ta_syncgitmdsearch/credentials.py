"""Read and write Git secrets via Splunk storage/passwords (password.conf)."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote

from ta_syncgitmdsearch.constants import (
    APP_NAME,
    PASSWORD_REALM,
    PASSWORD_USER_AUTH,
    PASSWORD_USER_SSH,
)
from ta_syncgitmdsearch.splunk_rest import SplunkRestError, request


MASKED = "********"


def load_secrets(session_key: str) -> Dict[str, Optional[str]]:
    status, payload = request(
        "/servicesNS/nobody/{}/storage/passwords".format(APP_NAME),
        session_key,
        getargs={"output_mode": "json", "count": "0"},
    )
    del status
    secrets = {"password": None, "ssh_private_key": None}  # type: Dict[str, Optional[str]]
    for entry in _entries(payload):
        content = entry.get("content") or {}
        realm = content.get("realm")
        username = content.get("username")
        clear_password = content.get("clear_password")
        if realm != PASSWORD_REALM:
            continue
        if username == PASSWORD_USER_AUTH:
            secrets["password"] = clear_password
        elif username == PASSWORD_USER_SSH:
            secrets["ssh_private_key"] = clear_password
    return secrets


def secret_flags(session_key: str) -> Dict[str, str]:
    secrets = load_secrets(session_key)
    return {
        "password_set": _flag(secrets.get("password")),
    }


def save_password(session_key: str, password: str) -> None:
    if not _should_store(password):
        return
    _upsert(session_key, PASSWORD_USER_AUTH, password)


def _should_store(value: Optional[str]) -> bool:
    if not value:
        return False
    return value.strip() not in ("", MASKED)


def _upsert(session_key: str, username: str, password: str) -> None:
    if _has_credential(session_key, username):
        _update_password(session_key, username, password)
        return
    try:
        _create_password(session_key, username, password)
    except SplunkRestError as exc:
        already_exists = exc.status in (400, 409) and "already exist" in str(exc).lower()
        if not already_exists:
            raise
        _update_password(session_key, username, password)


def _has_credential(session_key: str, username: str) -> bool:
    _, payload = request(
        "/servicesNS/nobody/{}/storage/passwords".format(APP_NAME),
        session_key,
        getargs={"output_mode": "json", "count": "0"},
    )
    expected_names = (
        "credential:{}:{}:".format(PASSWORD_REALM, username),
        "{}:{}:".format(PASSWORD_REALM, username),
    )
    for entry in _entries(payload):
        content = entry.get("content") or {}
        if content.get("realm") == PASSWORD_REALM and content.get("username") == username:
            return True
        name = entry.get("name") or content.get("name") or ""
        if name in expected_names:
            return True
    return False


def _create_password(session_key: str, username: str, password: str) -> None:
    request(
        "/servicesNS/nobody/{}/storage/passwords".format(APP_NAME),
        session_key,
        method="POST",
        postargs={
            "name": username,
            "password": password,
            "realm": PASSWORD_REALM,
        },
    )


def _update_password(session_key: str, username: str, password: str) -> None:
    encoded = quote("credential:{}:{}:".format(PASSWORD_REALM, username), safe="")
    request(
        "/servicesNS/nobody/{}/storage/passwords/{}".format(APP_NAME, encoded),
        session_key,
        method="POST",
        postargs={"password": password},
    )


def _entries(payload: Any):
    if isinstance(payload, dict):
        return payload.get("entry") or []
    return []


def _flag(value: Optional[str]) -> str:
    return "1" if value else "0"
