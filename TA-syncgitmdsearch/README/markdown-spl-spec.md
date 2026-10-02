# Markdown SPL 文書規約

`syncgitmdsearch` は **1つの `.md` ファイル = 1つの saved search** として扱います。検索名はファイル名から `.md` を除いた値です（例: `error_count.md` → `error_count`）。

同名ファイルが複数ディレクトリにある場合はエラーになります。上書きしたいときだけ front matter の `search_name` を使ってください。

## 抽出の優先順位

上から最初に確定した 1件だけを採用します。

| 優先度 | 方法 | 用途 |
|--------|------|------|
| 0 | YAML front matter の `search:` | savedsearches.conf と同じ明示指定 |
| 1 | コードフェンス `spl main` / `spl-main` | 複数ブロックがあるときの本命 |
| 2 | `<!-- spl:start -->` ... `<!-- spl:end -->` | 他言語のコードフェンスと混在するとき |
| 3 | 言語タグ `spl` / `splunk` / `splunk-spl` / `splunkql` が **1つ** | **推奨デフォルト** |
| 4 | 上記タグが複数 + `combine_spl_blocks: true` | 意図的に連結する場合のみ |
| 5 | 見出し `Search` / `SPL` / `サーチ` / `検索` の直後のフェンス | ドキュメント向け |
| 6 | ファイル内のフェンスが **ちょうど1つ**（言語タグなし） | 簡易ファイル |

複数の `spl` フェンスがあり、`main` 指定も `combine_spl_blocks` もない場合は `multiple_spl_blocks` でスキップします。誤って説明用サンプルと本番サーチを連結しないためです。

## 推奨テンプレート

````markdown
---
description: ホスト別エラー件数
is_scheduled: false
dispatch.earliest_time: -24h
dispatch.latest_time: now
---

# ホスト別エラー件数

前日分のエラーをホストごとに集計します。

```spl
index=main sourcetype=app:error
| stats count by host
```
````

## Front matter

先頭の `---` で囲みます。コマンドが saved search に渡すキーは許可リストのみです。

許可するキー:

- `description`
- `is_scheduled`
- `cron_schedule`
- `schedule_window`
- `schedule_priority`
- `dispatch.earliest_time`
- `dispatch.latest_time`
- `dispatch.ttl`
- `is_visible`
- `disabled`
- `display.general.type`

コマンド内部だけが使うキー:

- `search` — SPL 本体（最優先）
- `search_name` — 検索名の上書き
- `skip` — `true` ならこのファイルを無視
- `combine_spl_blocks` — 複数 SPL を改行連結する

`search` の複数行は YAML の `|` が使えます。

```yaml
---
search: |
  index=main
  | stats count by host
---
```

アラートアクション（メール送信、スクリプト実行など）は front matter からは設定できません。

## コードフェンス

次の言語タグを SPL とみなします（大文字小文字は無視）。

- `spl`（推奨）
- `splunk`
- `splunk-spl`
- `splunkql`

本命ブロックの指定:

````markdown
```spl main
index=main | stats count
```
````

または `spl-main`。

## HTML コメント

````markdown
本文や他言語のサンプルのあと。

<!-- spl:start -->
index=main sourcetype=app:error
| stats count by host
<!-- spl:end -->
````

## 見出し規約

次の見出しの直後にあるフェンスを SPL とみなします。

- `Search`
- `Saved Search`
- `SPL`
- `サーチ`
- `検索`

## 無視するファイル

既定では次のファイル名を同期しません。

- `README.md`
- `CONTRIBUTING.md`
- `CHANGELOG.md`
- `LICENSE.md`

front matter で `skip: true` としたファイルも無視します。

## 既存 saved search との衝突

同期で作った検索には description 末尾に次のマーカーが付きます。

```text
[syncgitmdsearch source=path/to/file.md]
```

- マーカーがある検索は更新します
- マーカーがない検索は、設定の「上書き」がオフならスキップします
