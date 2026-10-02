# TA-syncgitmdsearch

Git リポジトリ上の Markdown から SPL を抽出し、ファイル名を検索名として Splunk の saved search に保存する Add-on です。カスタムコマンド名は `syncgitmdsearch` です。

## できること

1. 設定 GUI で Git 接続情報を保存する（シークレットは `password.conf` へ暗号化）
2. `| syncgitmdsearch` で Markdown を取得する
3. [Markdown SPL 規約](docs/markdown-spl-spec.md) に従って SPL を抽出する
4. 検索名 = ファイル名（`.md` なし）で saved search を作成 / 更新する

## 前提

- Splunk Enterprise 9.x / 10.x（Python 3）
- サーチヘッドに **Git** がインストールされ、Splunk 実行ユーザーの PATH で `git` が使えること
- Git リモートは `https://` または `ssh://` / `git@host:path` 形式

## インストール

1. `package.ps1` で `.spl` を作るか、`TA-syncgitmdsearch` フォルダを `$SPLUNK_HOME/etc/apps/` にコピーする
2. Splunk を再起動する（または `_reload` 可能な設定だけなら Debug/Refresh）
3. **Git Markdown Search Sync → Git 接続設定** を開く

## 設定 GUI

| 項目 | 保存先 | 秘密情報 |
|------|--------|----------|
| リポジトリ URL / ブランチ / glob | `ta_syncgitmdsearch.conf` | いいえ |
| ユーザー名 | 同上 | いいえ |
| パスワード / PAT | `password.conf`（storage/passwords） | はい |
| SSH 秘密鍵 | 同上 | はい |

URL に `https://user:token@host/...` を埋め込まないでください。コマンドは埋め込み認証を拒否します。

### 認証方式

- **HTTPS トークン**: パスワード欄に PAT。ユーザー名は空なら `git`
- **HTTPS Basic**: ユーザー名 + パスワード
- **SSH デプロイキー**: 暗号化されていない OpenSSH / PEM 秘密鍵。パスフレーズ付き鍵は非対応

## コマンド

```spl
| syncgitmdsearch
| syncgitmdsearch dry_run=true
| syncgitmdsearch overwrite=true
| syncgitmdsearch branch=develop md_glob="searches/*.md"
```

| オプション | 説明 |
|------------|------|
| `dry_run` | 抽出だけ行い saved search を書かない |
| `overwrite` | このコマンド以外が作った検索も更新する |
| `branch` | 設定のブランチを上書き |
| `md_glob` | リポジトリルートからの相対 glob |
| `target_app` | saved search の保存先アプリ |

出力フィールド: `filename`, `source_path`, `search_name`, `status`, `message`, `source`, `spl_preview`, `warning`

`status` の例: `created`, `updated`, `dry_run`, `skipped`, `skipped_exists`, `error`

## ディレクトリ構成

```text
TA-syncgitmdsearch/
  default/          commands.conf, restmap, 設定画面, 既定値
  bin/              syncgitmdsearch.py と抽出・Git・REST 実装
  appserver/static/ 設定 GUI
  lib/              同梱 splunklib（searchcommands）
  README/           ta_syncgitmdsearch.conf.spec
```

## セキュリティ

- 認証情報はソースにハードコードしません
- Git URL の `http://` と URL 埋め込みパスワードは拒否します
- HTTPS の証明書検証は既定で有効です
- 設定 REST は `admin_all_objects` が必要です
- Git 呼び出しはシェルを使わず引数配列で実行します
