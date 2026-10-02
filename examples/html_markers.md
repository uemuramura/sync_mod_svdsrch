他言語サンプルと本番サーチを混在させる例です。

```bash
echo "not spl"
```

<!-- spl:start -->
index=main sourcetype=app:error
| stats count by host
<!-- spl:end -->
