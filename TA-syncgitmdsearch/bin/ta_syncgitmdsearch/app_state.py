"""Mark the add-on as configured at app scope (not user-local)."""

from __future__ import annotations

from ta_syncgitmdsearch.constants import APP_NAME
from ta_syncgitmdsearch.splunk_rest import SplunkRestError, request


def mark_app_configured(session_key: str) -> None:
    """Set install.is_configured via the apps/local EAI endpoint.

    writeConf('app', ...) from an MConfigHandler often lands in a user
    directory, so Splunk keeps showing the built-in App configuration page.
    """
    paths = (
        "/servicesNS/nobody/system/apps/local/{}".format(APP_NAME),
        "/services/apps/local/{}".format(APP_NAME),
    )
    last_error = None
    for path in paths:
        try:
            request(
                path,
                session_key,
                method="POST",
                postargs={"configured": "1"},
            )
            return
        except SplunkRestError as exc:
            last_error = exc
    if last_error:
        raise last_error
