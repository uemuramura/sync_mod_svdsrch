"""Load non-secret add-on settings and apply command-line overrides."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ta_syncgitmdsearch.constants import (
    ALLOWED_AUTH_TYPES,
    ALLOWED_PROVIDERS,
    APP_NAME,
    AUTH_HTTPS_TOKEN,
    CONF_FILE,
    CONF_STANZA,
    DEFAULT_SKIP_FILES,
    PROVIDER_AUTO,
)
from ta_syncgitmdsearch.url_util import validate_git_url, validate_https_url

TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def load_settings(session_key: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from ta_syncgitmdsearch.splunk_rest import request

    _, payload = request(
        "/servicesNS/nobody/{}/configs/conf-{}/{}".format(
            APP_NAME, CONF_FILE, CONF_STANZA
        ),
        session_key,
        getargs={"output_mode": "json"},
    )
    content = {}
    entries = payload.get("entry") if isinstance(payload, dict) else None
    if entries:
        content = entries[0].get("content") or {}
    merged = _defaults()
    for key in merged:
        if key in content and content[key] not in (None, ""):
            merged[key] = content[key]
    if overrides:
        for key, value in overrides.items():
            if value is not None:
                merged[key] = value
    return normalize_settings(merged)


def _defaults() -> Dict[str, Any]:
    return {
        "repo_url": "",
        "branch": "main",
        "md_glob": "**/*.md",
        "provider": PROVIDER_AUTO,
        "api_base_url": "",
        "auth_type": AUTH_HTTPS_TOKEN,
        "username": "",
        "target_app": APP_NAME,
        "target_owner": "nobody",
        "overwrite": False,
        "skip_files": ",".join(DEFAULT_SKIP_FILES),
    }


def normalize_settings(raw: Dict[str, Any]) -> Dict[str, Any]:
    settings = dict(raw)
    settings["repo_url"] = validate_git_url(str(settings.get("repo_url") or ""))
    settings["branch"] = _validate_branch(str(settings.get("branch") or "main"))
    settings["md_glob"] = _validate_glob(str(settings.get("md_glob") or "**/*.md"))
    provider = str(settings.get("provider") or PROVIDER_AUTO).strip().lower()
    if provider not in ALLOWED_PROVIDERS:
        raise ValueError("provider must be one of: {}".format(", ".join(ALLOWED_PROVIDERS)))
    settings["provider"] = provider
    api_base = str(settings.get("api_base_url") or "").strip()
    settings["api_base_url"] = (
        validate_https_url(api_base, "api_base_url") if api_base else ""
    )
    auth_type = str(settings.get("auth_type") or AUTH_HTTPS_TOKEN).strip()
    if auth_type == "ssh_key":
        raise ValueError("SSH is not supported. Use https_token or https_basic.")
    if auth_type not in ALLOWED_AUTH_TYPES:
        raise ValueError("auth_type must be one of: {}".format(", ".join(ALLOWED_AUTH_TYPES)))
    settings["auth_type"] = auth_type
    settings["username"] = _validate_username(str(settings.get("username") or ""))
    settings["target_app"] = _validate_ident(
        str(settings.get("target_app") or APP_NAME), "target_app"
    )
    settings["target_owner"] = _validate_ident(
        str(settings.get("target_owner") or "nobody"), "target_owner"
    )
    settings["overwrite"] = _as_bool(settings.get("overwrite"))
    settings["skip_files"] = _validate_skip_files(str(settings.get("skip_files") or ""))
    return settings


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in TRUE_VALUES


def _validate_branch(value: str) -> str:
    import re

    cleaned = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", cleaned) or cleaned.startswith("-"):
        raise ValueError("branch contains invalid characters")
    return cleaned


def _validate_glob(value: str) -> str:
    cleaned = value.strip().replace("\\", "/")
    if not cleaned:
        raise ValueError("md_glob is required")
    if cleaned.startswith("/") or ":" in cleaned or ".." in cleaned.split("/"):
        raise ValueError("md_glob must be a relative path inside the repository")
    return cleaned


def _validate_username(value: str) -> str:
    cleaned = value.strip()
    if any(char in cleaned for char in ("\n", "\r", "\x00")):
        raise ValueError("username contains invalid characters")
    if len(cleaned) > 128:
        raise ValueError("username is too long")
    return cleaned


def _validate_ident(value: str, field: str) -> str:
    import re

    cleaned = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", cleaned):
        raise ValueError("{} contains invalid characters".format(field))
    return cleaned


def _validate_skip_files(value: str) -> str:
    names = []
    for item in value.split(","):
        name = item.strip()
        if not name:
            continue
        if "/" in name or "\\" in name or ".." in name:
            raise ValueError("skip_files must be file names, not paths")
        names.append(name)
    return ",".join(names)
