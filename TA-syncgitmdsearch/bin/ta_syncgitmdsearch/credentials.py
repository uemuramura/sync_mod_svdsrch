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
        "ssh_key_set": _flag(secrets.get("ssh_private_key")),
    }


def save_password(session_key: str, password: str) -> None:
    if not _should_store(password):
        return
    _upsert(session_key, PASSWORD_USER_AUTH, password)


def save_ssh_key(session_key: str, ssh_private_key: str) -> None:
    if not _should_store(ssh_private_key):
        return
    cleaned = ssh_private_key.replace("\r\n", "\n").strip() + "\n"
    if "ENCRYPTED" in cleaned:
        raise ValueError("Encrypted SSH keys are not supported. Use an unencrypted deploy key.")
    if "BEGIN" not in cleaned or "PRIVATE KEY" not in cleaned:
        raise ValueError("ssh_private_key must be an OpenSSH or PEM private key")
    _upsert(session_key, PASSWORD_USER_SSH, cleaned)


def _should_store(value: Optional[str]) -> bool:
    if not value:
        return False
    return value.strip() not in ("", MASKED)


def _upsert(session_key: str, username: str, password: str) -> None:
    encoded = quote("{}:{}:".format(PASSWORD_REALM, username), safe="")
    update_path = "/servicesNS/nobody/{}/storage/passwords/{}".format(APP_NAME, encoded)
    try:
        request(
            update_path,
            session_key,
            method="POST",
            postargs={"password": password},
        )
        return
    except SplunkRestError as exc:
        if exc.status not in (404, 400):
            raise
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


def _entries(payload: Any):
    if isinstance(payload, dict):
        return payload.get("entry") or []
    return []


def _flag(value: Optional[str]) -> str:
    return "1" if value else "0"
