# 設計判断記録 (Design Decisions)

このドキュメントでは、BackcastPro開発における重要なアーキテクチャ上の決定とその背景（Context）、および変更内容を記録します。

## 目次

1. [FTP廃止とGoogle Driveへの完全移行](#ftp廃止とgoogle-driveへの完全移行)
2. [株価データ更新のCloud Run Job化](#株価データ更新のcloud-run-job化)
3. [DockerfileのENTRYPOINT化](#dockerfileのentrypoint化)

---

## FTP廃止とGoogle Driveへの完全移行

**Date:** 2026-02-09  
**Status:** Implemented

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
**Status:** Implemented

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
    *   dry-run (`--args="--codes,7203,--days,3,--dry-run"`) が正常に動作することを確認済み。
*   **注意点**:
    *   `ENTRYPOINT` を使う場合、`docker run` でコマンドを上書きするには `--entrypoint` フラグが必要になる（デバッグ時に `bash` でコンテナに入る場合など）。

---
