"""REST handler for add-on settings. Secrets go to storage/passwords only."""

from __future__ import annotations

import os
import sys

BIN_DIR = os.path.dirname(os.path.abspath(__file__))
if BIN_DIR not in sys.path:
    sys.path.insert(0, BIN_DIR)

import splunk.admin as admin

from ta_syncgitmdsearch.app_state import mark_app_configured
from ta_syncgitmdsearch.config import normalize_settings
from ta_syncgitmdsearch.constants import CONF_FILE, CONF_STANZA
from ta_syncgitmdsearch.credentials import save_password, secret_flags
from ta_syncgitmdsearch.splunk_rest import SplunkRestError

PUBLIC_FIELDS = (
    "repo_url",
    "branch",
    "md_glob",
    "provider",
    "api_base_url",
    "auth_type",
    "username",
    "target_app",
    "target_owner",
    "overwrite",
    "skip_files",
)
SECRET_FIELDS = ("password",)


class SettingsHandler(admin.MConfigHandler):
    def setup(self):
        if self.requestedAction in (admin.ACTION_EDIT, admin.ACTION_CREATE):
            for name in PUBLIC_FIELDS + SECRET_FIELDS:
                self.supportedArgs.addOptArg(name)

    def handleList(self, conf_info):
        conf = self.readConf(CONF_FILE) or {}
        stanza = conf.get(CONF_STANZA, {})
        item = conf_info[CONF_STANZA]
        for name in PUBLIC_FIELDS:
            item[name] = stanza.get(name, "")
        item["password"] = ""
        flags = secret_flags(self.getSessionKey())
        item["password_set"] = flags["password_set"]

    def handleEdit(self, conf_info):
        existing = (self.readConf(CONF_FILE) or {}).get(CONF_STANZA, {})
        incoming = {}
        keep_if_blank = ("skip_files",)
        for name in PUBLIC_FIELDS:
            value = self._arg(name)
            if value == "" and name in keep_if_blank:
                incoming[name] = existing.get(name, "")
            else:
                incoming[name] = value
        try:
            normalized = normalize_settings(incoming)
        except ValueError as exc:
            raise admin.ArgValidationException(str(exc))
        writable = {key: _conf_value(normalized[key]) for key in PUBLIC_FIELDS}
        self.writeConf(CONF_FILE, CONF_STANZA, writable)
        try:
            save_password(self.getSessionKey(), self._arg("password"))
            mark_app_configured(self.getSessionKey())
        except (ValueError, SplunkRestError) as exc:
            raise admin.ArgValidationException(str(exc))
        self.handleList(conf_info)

    def handleCreate(self, conf_info):
        self.handleEdit(conf_info)

    def _arg(self, name):
        values = self.callerArgs.data.get(name)
        if not values:
            return ""
        value = values[0] if isinstance(values, (list, tuple)) else values
        if value is None:
            return ""
        return str(value)


def _conf_value(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


admin.init(SettingsHandler, admin.CONTEXT_APP_AND_USER)
