"""Fetch Markdown from Git hosts over HTTPS. No git binary and no disk cache."""

from __future__ import annotations

import fnmatch
import io
import os
import ssl
import zipfile
from base64 import b64encode
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from ta_syncgitmdsearch.constants import (
    APP_NAME,
    AUTH_HTTPS_BASIC,
    AUTH_HTTPS_TOKEN,
    PROVIDER_AUTO,
    PROVIDER_BITBUCKET,
    PROVIDER_GITHUB,
    PROVIDER_GITLAB,
)
from ta_syncgitmdsearch.redact import redact_text
from ta_syncgitmdsearch.url_util import parse_https_repo, validate_https_url

MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_MD_BYTES = 2 * 1024 * 1024
HTTP_TIMEOUT_SECONDS = 60
USER_AGENT = APP_NAME + "/1.1"


class HttpGitError(RuntimeError):
    pass


@dataclass
class MarkdownFile:
    relpath: str
    content: str


class _HttpsOnlyRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not str(newurl).startswith("https://"):
            raise HttpGitError("Refusing non-HTTPS redirect")
        return HTTPRedirectHandler.redirect_request(
            self, req, fp, code, msg, headers, newurl
        )


def fetch_markdown_files(settings: Dict, secrets: Dict[str, Optional[str]]) -> List[MarkdownFile]:
    repo_url = validate_https_url(settings["repo_url"], "repo_url")
    host, path_parts = parse_https_repo(repo_url)
    provider = resolve_provider(str(settings.get("provider") or PROVIDER_AUTO), host)
    archive_url = build_archive_url(
        provider,
        host,
        path_parts,
        settings["branch"],
        str(settings.get("api_base_url") or ""),
    )
    headers = _auth_headers(
        settings.get("auth_type") or AUTH_HTTPS_TOKEN,
        settings.get("username") or "",
        secrets.get("password") or "",
        provider,
    )
    payload = _https_get(archive_url, headers, secrets.get("password") or "")
    return extract_markdown_from_zip(
        payload,
        settings["md_glob"],
        str(settings.get("skip_files") or ""),
    )


def resolve_provider(provider: str, host: str) -> str:
    lowered = (provider or PROVIDER_AUTO).strip().lower()
    host = (host or "").lower()
    if lowered == PROVIDER_AUTO:
        if host == "github.com" or host.endswith(".github.com"):
            return PROVIDER_GITHUB
        if host == "gitlab.com" or host.endswith(".gitlab.com") or "gitlab" in host:
            return PROVIDER_GITLAB
        if host == "bitbucket.org" or host.endswith(".bitbucket.org"):
            return PROVIDER_BITBUCKET
        raise HttpGitError(
            "Could not detect Git host. Set provider to github, gitlab, or bitbucket."
        )
    if lowered not in (PROVIDER_GITHUB, PROVIDER_GITLAB, PROVIDER_BITBUCKET):
        raise HttpGitError("provider must be auto, github, gitlab, or bitbucket")
    return lowered


def build_archive_url(
    provider: str, host: str, path_parts: List[str], branch: str, api_base_url: str
) -> str:
    if len(path_parts) < 2:
        raise HttpGitError("Repository URL must include owner/group and project name")
    ref = quote(branch, safe="")
    if provider == PROVIDER_GITHUB:
        owner, repo = path_parts[0], path_parts[1]
        api_root = _api_root(api_base_url, host, default_github=True)
        return "{}/repos/{}/{}/zipball/{}".format(api_root, quote(owner), quote(repo), ref)
    if provider == PROVIDER_GITLAB:
        project = quote("/".join(path_parts), safe="")
        api_root = _api_root(api_base_url, host, default_github=False, gitlab=True)
        return "{}/projects/{}/repository/archive.zip?sha={}".format(api_root, project, ref)
    workspace, repo = path_parts[0], path_parts[1]
    if api_base_url.strip():
        root = validate_https_url(api_base_url.strip().rstrip("/"), "api_base_url")
        return "{}/{}/{}/get/{}.zip".format(root, quote(workspace), quote(repo), ref)
    return "https://bitbucket.org/{}/{}/get/{}.zip".format(
        quote(workspace), quote(repo), ref
    )


def extract_markdown_from_zip(
    payload: bytes, md_glob: str, skip_files: str
) -> List[MarkdownFile]:
    if not payload.startswith(b"PK"):
        raise HttpGitError("Host did not return a zip archive")
    skip = {name.lower() for name in skip_files.split(",") if name.strip()}
    found = []  # type: List[MarkdownFile]
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            relpath = zip_member_relpath(info.filename)
            if not relpath:
                continue
            filename = relpath.split("/")[-1]
            if filename.lower() in skip:
                continue
            if not filename.lower().endswith(".md"):
                continue
            if not match_repo_glob(relpath, md_glob):
                continue
            if info.file_size > MAX_MD_BYTES:
                raise HttpGitError("Markdown file is too large: {}".format(relpath))
            raw = archive.read(info)
            if len(raw) > MAX_MD_BYTES:
                raise HttpGitError("Markdown file is too large: {}".format(relpath))
            found.append(
                MarkdownFile(
                    relpath=relpath,
                    content=raw.decode("utf-8-sig", "replace"),
                )
            )
    return found


def zip_member_relpath(name: str) -> Optional[str]:
    parts = name.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    if len(parts) == 1:
        return parts[0]
    return "/".join(parts[1:])


def match_repo_glob(relpath: str, pattern: str) -> bool:
    normalized = relpath.replace("\\", "/")
    glob_pattern = (pattern or "**/*.md").replace("\\", "/")
    if glob_pattern == "**/*.md":
        return normalized.lower().endswith(".md")
    if fnmatch.fnmatch(normalized, glob_pattern):
        return True
    if "**/" in glob_pattern:
        suffix = glob_pattern.split("**/", 1)[1]
        parts = normalized.split("/")
        for index in range(len(parts)):
            if fnmatch.fnmatch("/".join(parts[index:]), suffix):
                return True
    return fnmatch.fnmatch(normalized.split("/")[-1], glob_pattern)


def _api_root(
    api_base_url: str,
    host: str,
    default_github: bool = False,
    gitlab: bool = False,
    bitbucket: bool = False,
) -> str:
    if api_base_url.strip():
        return validate_https_url(api_base_url.strip().rstrip("/"), "api_base_url")
    if default_github:
        if host in ("github.com", "www.github.com"):
            return "https://api.github.com"
        return "https://{}/api/v3".format(host)
    if gitlab:
        if host in ("gitlab.com", "www.gitlab.com"):
            return "https://gitlab.com/api/v4"
        return "https://{}/api/v4".format(host)
    if bitbucket:
        if host in ("bitbucket.org", "www.bitbucket.org"):
            return "https://bitbucket.org"
        return "https://{}".format(host)
    raise HttpGitError("Unsupported Git provider")


def _auth_headers(auth_type: str, username: str, password: str, provider: str) -> Dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/zip, application/octet-stream, */*",
    }
    if not password:
        return headers
    if auth_type == AUTH_HTTPS_BASIC:
        account = username or "git"
        token = b64encode("{}:{}".format(account, password).encode("utf-8")).decode("ascii")
        headers["Authorization"] = "Basic {}".format(token)
        return headers
    if auth_type != AUTH_HTTPS_TOKEN:
        raise HttpGitError("SSH authentication is not supported. Use an HTTPS token.")
    if provider == PROVIDER_GITLAB:
        headers["PRIVATE-TOKEN"] = password
        return headers
    if provider == PROVIDER_BITBUCKET:
        account = username or "x-token-auth"
        token = b64encode("{}:{}".format(account, password).encode("utf-8")).decode("ascii")
        headers["Authorization"] = "Basic {}".format(token)
        return headers
    headers["Authorization"] = "Bearer {}".format(password)
    return headers


def _https_get(url: str, headers: Dict[str, str], secret: str) -> bytes:
    validate_https_url(url, "archive_url")
    request = Request(url, headers=headers, method="GET")
    opener = build_opener(
        ProxyHandler({}),
        _HttpsOnlyRedirectHandler(),
        HTTPSHandler(context=_tls_context()),
    )
    try:
        with opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            if not str(final_url).startswith("https://"):
                raise HttpGitError("Refusing non-HTTPS response URL")
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_ARCHIVE_BYTES:
                raise HttpGitError("Repository archive exceeds the 50 MB limit")
            chunks = []
            total = 0
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise HttpGitError("Repository archive exceeds the 50 MB limit")
                chunks.append(chunk)
            return b"".join(chunks)
    except HTTPError as exc:
        raise HttpGitError(_http_error(exc, secret))
    except URLError as exc:
        raise HttpGitError(redact_text("HTTPS request failed: {}".format(exc.reason), [secret]))


def _http_error(exc: HTTPError, secret: str) -> str:
    detail = "HTTPS {} from Git host".format(exc.code)
    if exc.code in (401, 403):
        detail = "Git host rejected the credentials or the repository is private"
    elif exc.code == 404:
        detail = "Repository, branch, or archive API was not found"
    return redact_text(detail, [secret])


def _tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if hasattr(ssl, "TLSVersion"):
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    home = os.environ.get("SPLUNK_HOME")
    if home:
        cacert = os.path.join(home, "etc", "auth", "cacert.pem")
        if os.path.isfile(cacert):
            context.load_verify_locations(cacert)
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    return context
