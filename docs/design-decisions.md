# 設計判断記録 (Design Decisions)

このドキュメントでは、BackcastPro開発における重要なアーキテクチャ上の決定とその背景（Context）、および変更内容を記録します。

## 目次

1. [FTP廃止とGoogle Driveへの完全移行](#ftp廃止とgoogle-driveへの完全移行)
2. [株価データ更新のCloud Run Job化](#株価データ更新のcloud-run-job化)

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
