# TA-syncgitmdsearch

GitHub / GitLab / Bitbucket 上の Markdown を **HTTPS API** で取得し、ファイル名を検索名として Splunk の saved search に保存する Add-on です。コマンド名は `syncgitmdsearch` です。

`git` コマンド、SSH、サーチヘッド上の clone は使いません。Splunk Cloud の App Vetting で落ちやすい subprocess / アプリ外書き込みを避けています。

## できること

1. 設定 GUI で HTTPS 接続情報を保存する（シークレットは `password.conf` へ暗号化）
2. リポジトリの zip アーカイブをメモリ上で展開する
3. [Markdown SPL 規約](docs/markdown-spl-spec.md) に従って SPL を抽出する
4. 検索名 = ファイル名（`.md` なし）で saved search を作成 / 更新する

## 前提

- Splunk Enterprise 9.x / 10.x または Splunk Cloud（Python 3）
- リポジトリ URL は `https://` のみ
- GitHub、GitLab、Bitbucket（自動判定。GitHub Enterprise / 自前 GitLab は API ベース URL を指定）

## インストール

1. `package.ps1` で `.spl` を作るか、`TA-syncgitmdsearch` を `$SPLUNK_HOME/etc/apps/` に置く
2. Splunk を再起動する
3. **Git Markdown Search Sync → Git 接続設定** で URL とトークンを保存する

Splunk Cloud では AppInspect（`cloud` または `private_victoria` / `private_classic`）に通してからアップロードしてください。

## 設定

| 項目 | 保存先 | 秘密情報 |
|------|--------|----------|
| リポジトリ URL / ブランチ / glob / provider | `ta_syncgitmdsearch.conf` | いいえ |
| ユーザー名 | 同上 | いいえ |
| パスワード / PAT | `password.conf` | はい |

URL に `https://user:token@host/` を埋め込まないでください。SSH URL は拒否します。TLS は常に検証します。

Cloud では saved search の保存先は既定でこのアプリ（`TA-syncgitmdsearch`）です。

## コマンド

```spl
| syncgitmdsearch
| syncgitmdsearch dry_run=true
| syncgitmdsearch overwrite=true
| syncgitmdsearch branch=develop md_glob="searches/*.md"
```

## Cloud 向けの制約

- Git バイナリも SSH も使わない
- 取得結果はディスクに書かない（zip をメモリ展開）
- アーカイブは 50 MB まで
- 認証は HTTPS トークンまたは Basic のみ
