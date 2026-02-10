# 設計判断記録 (Design Decisions)

このドキュメントでは、BackcastPro開発における重要なアーキテクチャ上の決定とその背景（Context）、および変更内容を記録します。

## 目次

1. [FTP廃止とGoogle Driveへの完全移行](#ftp廃止とgoogle-driveへの完全移行)
2. [株価データ更新のCloud Run Job化](#株価データ更新のcloud-run-job化)
3. [DockerfileのENTRYPOINT化](#dockerfileのentrypoint化)
4. [Google Drive廃止と自宅NAS（FTPS）への移行](#google-drive廃止と自宅nasftpsへの移行)
5. [Cloud Run Proxyアップロード廃止とDockerボリュームマウントへの移行](#cloud-run-proxyアップロード廃止とdockerボリュームマウントへの移行)
6. [Cloud Run Job廃止とSynology NAS Docker + DockerHubへの移行](#cloud-run-job廃止とsynology-nas-docker--dockerhubへの移行)
7. [FTPS廃止とローカルファイル配信への移行](#ftps廃止とローカルファイル配信への移行)

---

## FTP廃止とGoogle Driveへの完全移行

**Date:** 2026-02-09
**Status:** ~~Implemented~~ Superseded（[Google Drive廃止と自宅NAS（FTPS）への移行](#google-drive廃止と自宅nasftpsへの移行)により置換）

### Context

BackcastProのデータ取得は、当初以下の3段フォールバック構成でした：
1. Google Drive (Cloud Run API経由)
2. FTPサーバー
3. ローカルでの新規作成

しかし、FTPサーバーの運用コストと複雑さが課題となり、Google Drive (Cloud Run API) の信頼性が向上したため、FTPを廃止して構成を簡素化することにしました。

### Decision

*   **FTP関連コードの完全削除**: `ftp_client.py` および関連するテスト、設定を削除。
*   **Google Driveへの一本化**: データ取得およびアップロードのロジックを Google Drive (Cloud Run API) のみに変更。
*   **フォールバックの簡素化**: ローカルキャッシュになければ Cloud Run API からダウンロード、それもなければ新規作成、という2段階（実質1段階＋救済）に変更。

### Consequences

*   **メリット**:
    *   コードベースの削減と保守性の向上。
    *   `.env` や GitHub Secrets の設定項目減少によるセットアップの簡素化。
    *   外部依存サービスの削減。
*   **デメリット**:
    *   FTPサーバーというバックアップ手段がなくなる（ただしGoogle Driveの信頼性でカバー可能と判断）。

---

## 株価データ更新のCloud Run Job化

**Date:** 2026-02-09
**Status:** ~~Implemented~~ Superseded（アップロード経路は[Cloud Run Proxyアップロード廃止とDockerボリュームマウントへの移行](#cloud-run-proxyアップロード廃止とdockerボリュームマウントへの移行)により変更。実行環境は[Cloud Run Job廃止とSynology NAS Docker + DockerHubへの移行](#cloud-run-job廃止とsynology-nas-docker--dockerhubへの移行)により変更）

### Context

株価データの更新処理（`update_stocks_price.py`）は、複数のデータソース（Tachibana, Stooq, J-Quants）からデータを取得し、加工してアップロードするバッチ処理です。これを安定して夜間に定期実行する基盤が必要でした。

### Decision

*   **Cloud Run Jobの採用**: サーバーレスで長時間のバッチ処理が可能な Cloud Run Job を採用。
*   **コンテナ化**: `cloud-job/Dockerfile` を作成し、実行環境をコンテナ化。
*   **Cloud Schedulerによるトリガー**: 毎晩定刻に Job を実行するよう設定。
*   **アップロード経路の最適化**:
    *   当初案 (`shimmering-roaming-pillow.md`): Google Drive API を直接叩く `GDriveUploader` を新規作成する案。
    *   **採用案** (`typed-wiggling-cocoa.md`): 既存の Cloud Run Proxy サービスに `POST` エンドポイントを追加し、Job からは HTTP POST するだけの構成に変更。これにより Job 側の依存関係（Google API Client Library）と認証設定（サービスアカウントJSON）を削減し、構成を大幅に簡素化。

### Consequences

*   **メリット**:
    *   サーバー管理不要で安定した定期実行が可能。
    *   Job 側の実装が非常に軽量（`requests` ライブラリのみで完結）。
    *   Cloud Run Proxy にロジックを集約できたため、認証や権限管理が一元化された。

---

## DockerfileのENTRYPOINT化

**Date:** 2026-02-09
**Status:** Implemented

### Context

Cloud Run Job `update-stocks-price` が `--args` 付きで実行すると、exit code 1 で即座に失敗する問題が発生。アプリケーションログ（stdout/stderr）が一切出力されず、システムログには「Application exec likely failed」とだけ記録されていた。

原因は Docker の `CMD` と `ENTRYPOINT` の仕様の違い：

*   `CMD ["python", "script.py"]` の場合、Cloud Run Job の `args` フィールド（Kubernetes の `args`）は CMD を**完全に置換**する。つまり `--args="--codes,7203"` を渡すと、コンテナは `--codes` を実行ファイルとして実行しようとする。
*   `ENTRYPOINT ["python", "script.py"]` の場合、`args` は ENTRYPOINT の後ろに**引数として追加**される。

### Decision

`cloud-job/Dockerfile` の最終行を `CMD` から `ENTRYPOINT` に変更。

```dockerfile
# 変更前
CMD ["python", "/app/update_stocks_price.py"]

# 変更後
ENTRYPOINT ["python", "/app/update_stocks_price.py"]
```

### Consequences

*   **メリット**:
    *   `--args` が正しく Python スクリプトの引数として渡されるようになった。
    *   `--args="--codes,7203,--days,3"` が正常に動作することを確認済み。
*   **注意点**:
    *   `ENTRYPOINT` を使う場合、`docker run` でコマンドを上書きするには `--entrypoint` フラグが必要になる（デバッグ時に `bash` でコンテナに入る場合など）。

---

## Google Drive廃止と自宅NAS（FTPS）への移行

**Date:** 2026-02-10
**Status:** ~~Implemented~~ Superseded（[FTPS廃止とローカルファイル配信への移行](#ftps廃止とローカルファイル配信への移行)により置換）

### Context

[FTP廃止とGoogle Driveへの完全移行](#ftp廃止とgoogle-driveへの完全移行)で Google Drive に一本化したが、Google Drive API の制約（レート制限、API呼び出しの複雑さ、サービスアカウント管理）が運用上の課題となった。自宅に NAS（Synology DS218）が稼働しており、FTPS サーバーが利用可能であったため、ストレージを NAS に移行することを決定。

### Decision

*   **Cloud Run Proxy のバックエンドを Google Drive API → FTPS に変更**: `cloud-run/main.py` の `GoogleDriveProxy` クラスを `NASFtpsProxy` クラスに置換。
*   **プロトコル選定: FTPS（rsync ではなく）**: Cloud Run のリクエスト-レスポンスモデルとの親和性から FTPS を採用。rsync はバッチ同期向きで、オンデマンドの個別ファイル配信には不向き。
*   **HTTP API インターフェースは維持**: `GET /jp/<path:file_path>` と `POST /jp/<path:file_path>` はそのまま。クライアント側（`CloudRunClient`, `update_stocks_price.py`）の変更は不要。
*   **NAT 越え対応**: `_NatFriendlyFTP_TLS` クラスで PASV レスポンスのホストを制御接続のホストに差し替え。
*   **リクエストごとの接続確立**: Cloud Run コンテナはフリーズ/リサイクルされるため、接続プールは使わず毎リクエストで FTPS 接続を確立・切断。
*   **Google 依存ライブラリの完全削除**: `google-api-python-client`, `google-auth` を `requirements.txt` から削除。`ftplib`/`ssl` は Python 標準ライブラリのため追加依存なし。

### Consequences

*   **メリット**:
    *   Google Drive API のレート制限・複雑さから解放。
    *   Docker イメージサイズの削減（Google API Client の依存を除去）。
    *   ストレージ容量が NAS のディスク容量に依存し、Google Drive の容量制限なし。
    *   コードの大幅な簡素化（フォルダID検索が不要、パスベースの直接アクセス）。
*   **デメリット**:
    *   自宅ネットワーク・NAS の稼働率に依存（Google Drive の 99.9%+ SLA と比較）。
    *   NAS のインターネット公開が必要（FTPS ポートフォワーディング、DDNS）。

---

## Cloud Run Proxyアップロード廃止とDockerボリュームマウントへの移行

**Date:** 2026-02-10
**Status:** Implemented

### Context

`update_stocks_price.py`（Cloud Run Job）は、株価データをDuckDBに保存した後、`CloudRunClient` を使って Cloud Run Proxy 経由で NAS にアップロードしていた。しかし、Cloud Run Proxy を中継するアップロードは複雑さの原因であり、Dockerボリュームマウントで直接DuckDBファイルに書き込む方がシンプルで信頼性が高い。

### Decision

*   **`upload_to_cloud()` 関数の削除**: Cloud Run Proxy へのアップロード処理を完全に削除。
*   **`--dry-run` 引数の削除**: アップロードをスキップする目的のフラグだったため、不要に。
*   **Dockerボリュームマウント方式に変更**: `Dockerfile` に `ENV STOCKDATA_CACHE_DIR=/data` を追加。コンテナ実行時に `-v /host/path:/data` でマウントすることで、DuckDBファイルをホスト側に永続化。
*   **`UpdateSummary` の簡素化**: `uploaded` / `upload_failed` フィールドを削除。

### Consequences

*   **メリット**:
    *   Cloud Run Proxy への依存がなくなり、Job が自己完結型になった。
    *   `UPLOAD_API_KEY` と `BACKCASTPRO_NAS_PROXY_URL` が Job の環境変数から不要に。
    *   コードの大幅な簡素化（`upload_to_cloud` 関数52行 + 関連コード削除）。
    *   ローカルDocker環境でのテストが容易に（`docker run -v` のみで動作確認可能）。
*   **注意点**:
    *   Cloud Run Job で使用する場合は、ボリュームマウント（GCS FUSE等）の設定が別途必要。

---

## Cloud Run Job廃止とSynology NAS Docker + DockerHubへの移行

**Date:** 2026-02-10
**Status:** Implemented

### Context

`update_stocks_price.py` は Google Cloud Run Job で定期実行していたが、自宅に Synology NAS（DS218）が稼働しており、Docker 実行環境が利用可能。Cloud Run Job の課題（GCS FUSE マウント設定の複雑さ、Google Cloud のコスト）を解消するため、NAS の Docker で直接実行する構成に移行する。

### Decision

*   **実行環境の変更**: Google Cloud Run Job → Synology NAS の Docker。NAS のタスクスケジューラで定期実行。
*   **イメージ配布の変更**: Google Artifact Registry → DockerHub (`backcast/cloud-job`)。
*   **CI/CDの変更**: `cloudbuild-job.yaml`（Cloud Build）→ `.github/workflows/publish-dockerhub.yml`（GitHub Actions）。`main` ブランチへの push で自動ビルド・push。
*   **ボリュームマウント**: NAS のローカルディレクトリを `-v /volume1/docker/backcast/data:/data` でマウントし、DuckDB ファイルを永続化。

### Consequences

*   **メリット**:
    *   Google Cloud の運用コスト削減（Cloud Run Job、Cloud Scheduler、Artifact Registry）。
    *   GCS FUSE マウント設定が不要になり、構成がシンプルに。
    *   NAS のローカルディスクに直接書き込むため、データアクセスが高速。
    *   GitHub Actions + DockerHub というオープンな CI/CD パイプラインに統一。
*   **デメリット**:
    *   NAS の稼働率・ネットワーク環境に依存。
    *   DockerHub の pull rate limit（無料プラン: 100 pulls/6h）に注意が必要。

---

## FTPS廃止とローカルファイル配信への移行

**Date:** 2026-02-10
**Status:** Implemented

### Context

[Google Drive廃止と自宅NAS（FTPS）への移行](#google-drive廃止と自宅nasftpsへの移行)で Cloud Run Proxy のバックエンドを FTPS に変更したが、FTPS 接続の複雑さ（NAT 越え、SSL、per-request 接続）が不要なオーバーヘッドであった。NAS 上の Docker で Cloud Run Proxy を実行する場合、データディレクトリをボリュームマウントすればローカルファイルとして直接配信でき、FTPS を経由する必要がない。

### Decision

*   **FTPS 関連コードの完全削除**: `NASFtpsProxy` クラス、`_NatFriendlyFTP_TLS` クラス、`_get_proxy()` 関数を削除。`ftplib`、`ssl` のインポートも削除。
*   **`flask.send_from_directory` によるローカルファイル配信**: 環境変数 `DATA_DIR`（デフォルト: `/data`）で指定されたディレクトリからファイルを直接配信。
*   **ディレクトリ構造**: `{DATA_DIR}/jp/{file_path}`（例: `/data/jp/stocks_daily/1234.duckdb`）。
*   **HTTP API インターフェースは維持**: `GET /jp/<path:file_path>` はそのまま。クライアント側（`CloudRunClient`）の変更は不要。
*   **`ALLOWED_PATHS` ホワイトリストは維持**: セキュリティのためパス検証は継続。

### Consequences

*   **メリット**:
    *   コードの大幅な簡素化（165行 → 53行）。
    *   FTPS 接続の複雑さ（NAT 越え、SSL コンテキスト、per-request 接続）を排除。
    *   FTP 関連の環境変数（`FTPS_HOST`, `FTPS_PORT`, `FTPS_USERNAME`, `FTPS_PASSWORD` 等）が不要に。
    *   NAS のインターネット公開（FTPS ポートフォワーディング）が不要に。
    *   ボリュームマウント（`-v /volume1/docker/backcast/data:/data`）のみで動作。
*   **注意点**:
    *   Cloud Run で使用する場合は GCS バケットや NFS 等のボリュームマウント設定が必要。

### デプロイ

Docker でデプロイする場合、データが保存されているディレクトリを `/data` にマウントすれば、`DATA_DIR` のデフォルト値でそのまま動作します。

```bash
docker run -v /volume1/docker/backcast/data:/data -p 8080:8080 cloud-run
```

マウント先のディレクトリ構造:

```
/data/
  jp/
    stocks_daily/1234.duckdb
    stocks_board/8306.duckdb
    listed_info.duckdb
```

Cloud Run にデプロイする場合は、GCS バケットや NFS などのボリュームを `/data` にマウントしてください。

---
