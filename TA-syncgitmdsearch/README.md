# Git Markdown Search Sync

Custom command: `syncgitmdsearch`

Fetches Markdown over HTTPS from GitHub, GitLab, or Bitbucket. Tokens are stored in Splunk `password.conf`. The add-on does not run `git`, SSH, or write a repository cache to disk.

```
| syncgitmdsearch dry_run=true
| syncgitmdsearch
```
