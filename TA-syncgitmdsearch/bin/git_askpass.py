"""GIT_ASKPASS helper. Prints username or password based on the prompt.

Secrets come only from process environment variables set by git_sync.py.
"""

from __future__ import annotations

import os
import sys


def main() -> None:
    prompt = " ".join(sys.argv[1:]).lower()
    if "username" in prompt:
        sys.stdout.write(os.environ.get("SYNC_GIT_USERNAME", ""))
        return
    sys.stdout.write(os.environ.get("SYNC_GIT_PASSWORD", ""))


if __name__ == "__main__":
    main()
