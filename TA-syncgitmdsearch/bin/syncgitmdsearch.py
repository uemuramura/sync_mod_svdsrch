#!/usr/bin/env python
# coding=utf-8
"""Generating command: fetch Markdown from Git and save SPL as saved searches."""

from __future__ import annotations

import os
import sys
import time

BIN_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BIN_DIR)
LIB_DIR = os.path.join(APP_DIR, "lib")
for path in (BIN_DIR, LIB_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from splunklib.searchcommands import (  # noqa: E402
    Configuration,
    GeneratingCommand,
    Option,
    dispatch,
    validators,
)

from ta_syncgitmdsearch.config import load_settings  # noqa: E402
from ta_syncgitmdsearch.credentials import load_secrets  # noqa: E402
from ta_syncgitmdsearch.git_sync import GitError, GitRepo  # noqa: E402
from ta_syncgitmdsearch.md_parser import extract_spl  # noqa: E402
from ta_syncgitmdsearch.names import posix_relpath, search_name_from_path  # noqa: E402
from ta_syncgitmdsearch.redact import redact_text  # noqa: E402
from ta_syncgitmdsearch.savedsearch import upsert_savedsearch  # noqa: E402


@Configuration(type="reporting")
class SyncGitMdSearchCommand(GeneratingCommand):
    dry_run = Option(
        doc="Extract and report without writing saved searches",
        require=False,
        default=False,
        validate=validators.Boolean(),
    )
    overwrite = Option(
        doc="Replace saved searches that were not created by this command",
        require=False,
        default=None,
        validate=validators.Boolean(),
    )
    branch = Option(
        doc="Override the configured Git branch",
        require=False,
        default=None,
    )
    md_glob = Option(
        doc="Override the Markdown glob, relative to the repository root",
        require=False,
        default=None,
    )
    target_app = Option(
        doc="Override the app that stores saved searches",
        require=False,
        default=None,
    )

    def generate(self):
        started = time.time()
        session_key = self._metadata.searchinfo.session_key
        secret_values = []
        try:
            settings = load_settings(
                session_key,
                {
                    "overwrite": self.overwrite,
                    "branch": self.branch,
                    "md_glob": self.md_glob,
                    "target_app": self.target_app,
                },
            )
            secrets = load_secrets(session_key)
            secret_values = [secrets.get("password") or "", secrets.get("ssh_private_key") or ""]
            self._validate_auth(settings, secrets)
            with GitRepo(settings, secrets) as repo:
                files = repo.list_markdown_files()
                if repo.ssl_warning:
                    yield self._row(
                        status="warning",
                        message=repo.ssl_warning,
                        extra={"_time": started},
                    )
                if not files:
                    yield self._row(
                        status="error",
                        message="No Markdown files matched md_glob",
                        extra={"_time": started},
                    )
                    return
                seen_names = {}
                for path in files:
                    for row in self._process_file(
                        session_key, settings, repo.repo_dir, path, seen_names, secrets
                    ):
                        yield row
        except Exception as exc:
            yield self._row(
                status="error",
                message=redact_text(str(exc), secret_values),
                extra={"_time": started},
            )

    def _process_file(self, session_key, settings, repo_dir, path, seen_names, secrets):
        relpath = posix_relpath(path, repo_dir)
        filename = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                markdown = handle.read()
            parsed = extract_spl(markdown)
            search_name = parsed.search_name or search_name_from_path(path)
            if parsed.skip:
                yield self._row(
                    filename=filename,
                    source_path=relpath,
                    search_name=search_name,
                    status="skipped",
                    message="front matter skip=true",
                    source=parsed.source,
                )
                return
            if not parsed.ok:
                yield self._row(
                    filename=filename,
                    source_path=relpath,
                    search_name=search_name,
                    status="error",
                    message=parsed.error,
                )
                return
            if search_name in seen_names:
                yield self._row(
                    filename=filename,
                    source_path=relpath,
                    search_name=search_name,
                    status="error",
                    message="duplicate_search_name: {}".format(seen_names[search_name]),
                    source=parsed.source,
                )
                return
            seen_names[search_name] = relpath
            if self.dry_run:
                yield self._row(
                    filename=filename,
                    source_path=relpath,
                    search_name=search_name,
                    status="dry_run",
                    message="SPL extracted; saved search was not written",
                    source=parsed.source,
                    spl_preview=_preview(parsed.spl),
                    warning=parsed.warning,
                )
                return
            action = upsert_savedsearch(
                session_key,
                settings["target_app"],
                settings["target_owner"],
                search_name,
                parsed.spl,
                parsed.metadata,
                relpath,
                settings["overwrite"],
            )
            yield self._row(
                filename=filename,
                source_path=relpath,
                search_name=search_name,
                status=action,
                message="saved search {}".format(action),
                source=parsed.source,
                spl_preview=_preview(parsed.spl),
                warning=parsed.warning,
            )
        except Exception as exc:
            yield self._row(
                filename=filename,
                source_path=relpath,
                status="error",
                message=redact_text(str(exc), [secrets.get("password") or ""]),
            )

    def _validate_auth(self, settings, secrets):
        auth_type = settings["auth_type"]
        if auth_type in ("https_token", "https_basic") and not secrets.get("password"):
            raise GitError(
                "Git password or token is not configured. Open the add-on setup page."
            )
        if auth_type == "ssh_key" and not secrets.get("ssh_private_key"):
            raise GitError("SSH private key is not configured. Open the add-on setup page.")

    def _row(self, **fields):
        row = {"_time": time.time()}
        defaults = {
            "filename": "",
            "source_path": "",
            "search_name": "",
            "status": "",
            "message": "",
            "source": "",
            "spl_preview": "",
            "warning": "",
        }
        defaults.update(fields.pop("extra", {}))
        defaults.update(fields)
        row.update(defaults)
        return row


def _preview(spl, limit=300):
    compact = " ".join(spl.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


if __name__ == "__main__":
    dispatch(SyncGitMdSearchCommand, sys.argv, sys.stdin, sys.stdout, __name__)
