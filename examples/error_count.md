---
description: ホスト別エラー件数
dispatch.earliest_time: -24h
dispatch.latest_time: now
---

# ホスト別エラー件数

```spl
index=main sourcetype=app:error
| stats count by host
```
