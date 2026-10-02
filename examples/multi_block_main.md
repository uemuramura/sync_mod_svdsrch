説明用の断片と、本命サーチを分けます。

```spl
index=main
| head 1
```

完成形:

```spl main
index=main sourcetype=app:error
| stats count by host
```
