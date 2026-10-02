"""Clone or update a Git repository and list Markdown files."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from ta_syncgitmdsearch.constants import APP_NAME, AUTH_SSH_KEY
from ta_syncgitmdsearch.redact import redact_text
from ta_syncgitmdsearch.url_util import validate_git_url

GIT_TIMEOUT_SECONDS = 180
REMOTE_MARKER = ".syncgitmdsearch_remote"


class GitError(RuntimeError):
    pass


class GitRepo:
    def __init__(self, settings: Dict, secrets: Dict[str, Optional[str]], cache_dir: Optional[str] = None):
        self.settings = settings
        self.secrets = secrets
        self.repo_url = validate_git_url(settings["repo_url"])
        self.branch = settings["branch"]
        self.cache_dir = cache_dir or _default_cache_dir()
        self.repo_dir = os.path.join(self.cache_dir, "repo")
        self._tmpdir = None  # type: Optional[str]
        self._env = None  # type: Optional[Dict[str, str]]
        self.ssl_warning = ""

    def __enter__(self) -> "GitRepo":
        os.makedirs(self.cache_dir, exist_ok=True)
        self._tmpdir = tempfile.mkdtemp(prefix="syncgitmdsearch_")
        self._env = self._build_env(self._tmpdir)
        self.sync()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        env = self._env or {}
        key_file = env.get("SYNC_GIT_KEYFILE")
        if key_file and os.path.isfile(key_file):
            _secure_delete(key_file)
        if self._tmpdir and os.path.isdir(self._tmpdir):
            shutil.rmtree(self._tmpdir, ignore_errors=True)
        self._tmpdir = None
        self._env = None

    def sync(self) -> None:
        if self._has_usable_clone():
            self._fetch_existing()
            return
        if os.path.isdir(self.repo_dir):
            shutil.rmtree(self.repo_dir)
        os.makedirs(self.cache_dir, exist_ok=True)
        self._run(
            [
                "clone",
                "--depth",
                "1",
                "--branch",
                self.branch,
                "--",
                self.repo_url,
                self.repo_dir,
            ],
            cwd=self.cache_dir,
        )
        _write_text(os.path.join(self.cache_dir, REMOTE_MARKER), self.repo_url)

    def list_markdown_files(self) -> List[str]:
        root = Path(self.repo_dir)
        glob_pattern = self.settings["md_glob"]
        skip = {
            name.lower()
            for name in str(self.settings.get("skip_files") or "").split(",")
            if name.strip()
        }
        found = []
        for path in sorted(root.glob(glob_pattern)):
            if not path.is_file():
                continue
            if path.suffix.lower() != ".md":
                continue
            if path.name.lower() in skip:
                continue
            resolved = path.resolve()
            if not _is_within(str(resolved), self.repo_dir):
                continue
            found.append(str(resolved))
        return found

    def _has_usable_clone(self) -> bool:
        git_dir = os.path.join(self.repo_dir, ".git")
        marker = os.path.join(self.cache_dir, REMOTE_MARKER)
        if not os.path.isdir(git_dir) or not os.path.isfile(marker):
            return False
        previous = _read_text(marker).strip()
        return previous == self.repo_url

    def _fetch_existing(self) -> None:
        self._run(["fetch", "--depth", "1", "origin", self.branch], cwd=self.repo_dir)
        self._run(["checkout", "-B", self.branch, "FETCH_HEAD"], cwd=self.repo_dir)
        self._run(["reset", "--hard", "FETCH_HEAD"], cwd=self.repo_dir)
        self._run(["clean", "-fd"], cwd=self.repo_dir)

    def _build_env(self, tmpdir: str) -> Dict[str, str]:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GCM_INTERACTIVE"] = "never"
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "core.askPass"
        if not self.settings.get("verify_ssl", True):
            env["GIT_SSL_NO_VERIFY"] = "1"
            self.ssl_warning = "Git SSL verification is disabled"
        auth_type = self.settings.get("auth_type")
        username = self.settings.get("username") or (
            "git" if auth_type != AUTH_SSH_KEY else "git"
        )
        password = self.secrets.get("password") or ""
        askpass = _write_askpass_wrapper(tmpdir)
        env["GIT_ASKPASS"] = askpass
        env["SYNC_GIT_USERNAME"] = username
        env["SYNC_GIT_PASSWORD"] = password
        env["GIT_CONFIG_VALUE_0"] = askpass
        if auth_type == AUTH_SSH_KEY:
            key_material = self.secrets.get("ssh_private_key") or ""
            if not key_material.strip():
                raise GitError("SSH private key is not configured")
            key_file = _write_ssh_key(tmpdir, key_material)
            env["SYNC_GIT_KEYFILE"] = key_file
            strict = "yes" if self.settings.get("ssh_strict_host_key", True) else "accept-new"
            env["GIT_SSH_COMMAND"] = "ssh -i {} -o IdentitiesOnly=yes -o StrictHostKeyChecking={}".format(
                _quote_ssh_path(key_file), strict
            )
        return env

    def _run(self, args: List[str], cwd: str) -> str:
        git_bin = self.settings["git_command"]
        command = [git_bin] + args
        try:
            proc = subprocess.run(
                command,
                cwd=cwd,
                env=self._env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=GIT_TIMEOUT_SECONDS,
                check=False,
            )
        except FileNotFoundError:
            raise GitError("git executable was not found. Install Git and ensure it is on PATH.")
        except subprocess.TimeoutExpired:
            raise GitError("git command timed out")
        stdout = proc.stdout.decode("utf-8", "replace") if proc.stdout else ""
        stderr = proc.stderr.decode("utf-8", "replace") if proc.stderr else ""
        secrets = [
            self.secrets.get("password") or "",
            self.secrets.get("ssh_private_key") or "",
        ]
        if proc.returncode != 0:
            detail = redact_text(stderr or stdout or "git failed", secrets)
            raise GitError(detail.strip() or "git command failed")
        return stdout


def _default_cache_dir() -> str:
    home = os.environ.get("SPLUNK_HOME")
    if home:
        return os.path.join(home, "var", "lib", APP_NAME)
    return os.path.join(tempfile.gettempdir(), APP_NAME)


def _write_askpass_wrapper(tmpdir: str) -> str:
    script = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "git_askpass.py")
    )
    python_exe = sys.executable
    if os.name == "nt":
        wrapper = os.path.join(tmpdir, "askpass.cmd")
        content = '@echo off\r\n"{}" "{}" %*\r\n'.format(python_exe, script)
        _write_text(wrapper, content)
        return wrapper
    wrapper = os.path.join(tmpdir, "askpass.sh")
    content = '#!/bin/sh\nexec "{}" "{}" "$@"\n'.format(python_exe, script)
    _write_text(wrapper, content)
    os.chmod(wrapper, 0o700)
    return wrapper


def _write_ssh_key(tmpdir: str, material: str) -> str:
    key_file = os.path.join(tmpdir, "id_deploy")
    text = material.replace("\r\n", "\n").strip() + "\n"
    _write_text(key_file, text)
    os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)
    if os.name == "nt":
        _restrict_windows_acl(key_file)
    return key_file


def _restrict_windows_acl(path: str) -> None:
    import getpass
    import re

    user = getpass.getuser()
    if not re.fullmatch(r"[\w.\\-]+", user or ""):
        return
    subprocess.run(
        ["icacls", path, "/inheritance:r"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    subprocess.run(
        ["icacls", path, "/grant:r", "{}:(R)".format(user)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _quote_ssh_path(path: str) -> str:
    return '"' + path.replace('"', "") + '"'


def _is_within(child: str, parent: str) -> bool:
    child_abs = os.path.normcase(os.path.abspath(child))
    parent_abs = os.path.normcase(os.path.abspath(parent))
    try:
        common = os.path.commonpath([child_abs, parent_abs])
    except ValueError:
        return False
    return common == parent_abs


def _write_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _secure_delete(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
