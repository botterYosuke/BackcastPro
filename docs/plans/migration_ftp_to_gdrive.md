# FTPダウンロードをGoogle Drive (Cloud Run API経由) に変更

## Context
BackcastProは .duckdb ファイルのダウンロードにFTPを使用している。
これをGoogle Drive共有フォルダからのダウンロードに切り替える。
Google Cloud Run上にダウンロードプロキシAPIを構築予定（別途実装）で、
BackcastPro側はそのAPIにHTTP GETリクエストを送るだけのシンプルな設計にする。

Cloud Run APIのエンドポイント例:
```
GET {API_BASE_URL}/download/stocks_daily/1234.duckdb → ファイル本体をストリーム返却
GET {API_BASE_URL}/download/stocks_board/1234.duckdb → ファイル本体をストリーム返却
GET {API_BASE_URL}/download/listed_info.duckdb       → ファイル本体をストリーム返却
```

## 変更ファイル一覧

### 1. 新規作成: `src/BackcastPro/api/gdrive_client.py`
Google Driveダウンロードクライアント（Cloud Run API経由）

```python
@dataclass
class GDriveConfig:
    api_base_url: str  # Cloud Run APIのベースURL

    @classmethod
    def from_environment(cls) -> "GDriveConfig":
        # 環境変数 BACKCASTPRO_GDRIVE_API_URL から読み込み

    def is_configured(self) -> bool:
        return bool(self.api_base_url)


class GDriveClient:
    def download_file(self, remote_path: str, local_path: str) -> bool:
        """Cloud Run APIからファイルをストリームダウンロード"""
        # GET {api_base_url}/download/{remote_path}
        # requests.get(url, stream=True) でストリーミング書き込み
        # 失敗時は部分ファイル削除（FTPClientと同じパターン）

    def download_stocks_daily(self, code: str, local_path: str) -> bool:
        return self.download_file(f"stocks_daily/{code}.duckdb", local_path)

    def download_stocks_board(self, code: str, local_path: str) -> bool:
        return self.download_file(f"stocks_board/{code}.duckdb", local_path)

    def download_listed_info(self, local_path: str) -> bool:
        return self.download_file("listed_info.duckdb", local_path)
```

### 2. 変更: `src/BackcastPro/api/db_stocks_daily.py` (L462-470)
`_download_from_ftp` メソッドを修正。Google Drive優先、FTPフォールバック。

```python
def _download_from_ftp(self, code: str, local_path: str) -> bool:
    # 1. Google Drive (Cloud Run API) を試行
    from .gdrive_client import GDriveClient
    gdrive = GDriveClient()
    if gdrive.config.is_configured():
        if gdrive.download_stocks_daily(code, local_path):
            return True

    # 2. FTPフォールバック
    from .ftp_client import FTPClient
    client = FTPClient()
    if not client.config.is_configured():
        return False
    return client.download_stocks_daily(code, local_path)
```

### 3. 変更: `src/BackcastPro/api/db_stocks_board.py` (L427-435)
同じパターンで `_download_from_ftp` を修正。`download_stocks_board` を呼ぶ。

### 4. 変更: `src/BackcastPro/api/db_stocks_info.py` (L215-223)
同じパターンで `_download_from_ftp` を修正。`download_listed_info` を呼ぶ。
（codeパラメータなし）

### 5. 変更: `.env`
```ini
# ============================================
# Google Drive設定 (Cloud Run API経由)
# ============================================
BACKCASTPRO_GDRIVE_API_URL=https://<your-cloud-run-service>.run.app
```

### 6. 新規作成: `tests/test_gdrive_client.py`
- `GDriveConfig` の環境変数読み込みテスト
- `GDriveClient.download_file` の成功/失敗テスト（requestsをモック）
- 各便利メソッドのパス生成テスト
- ダウンロード失敗時の部分ファイル削除テスト

## FTPコードについて
- **削除しない** - アップロード機能がFTP依存のため残す
- Google Drive未設定時はFTPにフォールバック
- 将来的にGoogle Driveが安定したらFTPを削除可能

## 依存関係
- 新規依存なし（既存の `requests>=2.25.0` のみ使用）

## 検証方法
1. `tests/test_gdrive_client.py` のユニットテストを実行
2. Cloud Run APIデプロイ後、`.env` にURLを設定して手動テスト
3. ローカルの .duckdb ファイルを削除し、自動ダウンロードを確認
