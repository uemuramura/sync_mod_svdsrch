# Git Markdown Search Sync

Custom command: `syncgitmdsearch`

Install this folder under `$SPLUNK_HOME/etc/apps/`, restart Splunk, then open **Git 接続設定**. Git tokens and SSH keys are stored in Splunk `password.conf` via the setup page. Do not put secrets in source or in the Git URL.

Usage:

```
| syncgitmdsearch dry_run=true
| syncgitmdsearch
```
