"""Shared constants. Secrets are never stored here."""

APP_NAME = "TA-syncgitmdsearch"
COMMAND_NAME = "syncgitmdsearch"
CONF_FILE = "ta_syncgitmdsearch"
CONF_STANZA = "git"
PASSWORD_REALM = "TA-syncgitmdsearch"
PASSWORD_USER_AUTH = "git_auth"
PASSWORD_USER_SSH = "ssh_key"
SOURCE_MARKER_PREFIX = "[syncgitmdsearch source="
SOURCE_MARKER_SUFFIX = "]"

AUTH_HTTPS_TOKEN = "https_token"
AUTH_HTTPS_BASIC = "https_basic"
AUTH_SSH_KEY = "ssh_key"
ALLOWED_AUTH_TYPES = (AUTH_HTTPS_TOKEN, AUTH_HTTPS_BASIC, AUTH_SSH_KEY)

DEFAULT_SKIP_FILES = (
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "LICENSE.md",
)

# savedsearches.conf keys allowed from Markdown front matter.
ALLOWED_SAVEDSEARCH_KEYS = frozenset(
    (
        "description",
        "is_scheduled",
        "cron_schedule",
        "schedule_window",
        "schedule_priority",
        "dispatch.earliest_time",
        "dispatch.latest_time",
        "dispatch.ttl",
        "is_visible",
        "disabled",
        "display.general.type",
    )
)

BOOLEAN_SAVEDSEARCH_KEYS = frozenset(("is_scheduled", "is_visible", "disabled"))
