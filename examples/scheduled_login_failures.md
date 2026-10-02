---
description: 毎時のログイン失敗
is_scheduled: true
cron_schedule: 0 * * * *
dispatch.earliest_time: -70m@m
dispatch.latest_time: -10m@m
search: |
  index=main sourcetype=linux_secure action=failure
  | stats count by user
---

このファイルは front matter の `search` が最優先です。下の Python は無視されます。

```python
print("this is not the search")
```
