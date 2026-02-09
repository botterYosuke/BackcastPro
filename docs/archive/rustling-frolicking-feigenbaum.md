# FTPダウンロード処理の完全削除

## Context
BackcastProのデータ取得はGoogle Drive (Cloud Run API) → FTP → ローカル新規作成の3段フォールバック構成になっている。FTPは不要になったため、FTP関連のコードと設定を完全に削除し、Google Driveのみのダウンロードに簡素化する。

## 変更一覧

### 1. ファイル削除
- `src/BackcastPro/api/ftp_client.py` — 削除
- `tests/test_ftp_client.py` — 削除

### 2. `src/BackcastPro/api/db_stocks_daily.py`
`_download_from_ftp` → `_download_from_cloud` にリネームし、FTPフォールバック部分(L472-478)を削除、Google Driveのみに変更：
```python
def _download_from_cloud(self, code: str, local_path: str) -> bool:
    """Google DriveからDuckDBファイルをダウンロード"""
    from .gdrive_client import GDriveClient
    gdrive = GDriveClient()
    if gdrive.config.is_configured():
        if gdrive.download_stocks_daily(code, local_path):
            return True
        logger.debug(f"Google Driveからダウンロード失敗: stocks_daily/{code}.duckdb")
    return False
```
追加修正:
- L25: コメント「FTPからダウンロードを試行」→「クラウドからダウンロードを試行」
- L405: docstring「FTPからダウンロードを試行」→「クラウドからダウンロードを試行」
- L422-426: ログメッセージ「FTPから」→「クラウドから」、呼び出し `_download_from_ftp` → `_download_from_cloud`
- L450-454: 同上

### 3. `src/BackcastPro/api/db_stocks_board.py`
同様に `_download_from_ftp` → `_download_from_cloud` にリネーム、FTPフォールバック部分(L437-443)を削除、Google Driveのみに変更。
追加修正:
- L30: コメント「FTPからダウンロードを試行」→「クラウドからダウンロードを試行」
- L370: docstring「FTPからダウンロードを試行」→「クラウドからダウンロードを試行」
- L387-391, L415-419: ログメッセージ修正 + 呼び出しリネーム

### 4. `src/BackcastPro/api/db_stocks_info.py`
同様に `_download_from_ftp` → `_download_from_cloud` にリネーム、FTPフォールバック部分(L225-231)を削除、Google Driveのみに変更。
追加修正:
- L21: コメント「FTPからダウンロードを試行」→「クラウドからダウンロードを試行」
- L176: docstring「FTPからダウンロードを試行」→「クラウドからダウンロードを試行」
- L185-189, L203-207: ログメッセージ修正 + 呼び出しリネーム

### 5. API wrapper ファイル内のFTPコメント修正（6ファイル）
以下のコメント「FTPからダウンロードを試行」→「クラウドからダウンロードを試行」に修正：
- `src/BackcastPro/api/stocks_board.py` L25
- `src/BackcastPro/api/stocks_info.py` L21
- `src/BackcastPro/api/stocks_price.py` L35
- `src/trading_data/stocks_board.py` L30
- `src/trading_data/stocks_info.py` L43
- `src/trading_data/stocks_price.py` L80

### 6. テストファイルのFTP関連テスト修正
`tests/test_db_stocks_daily.py`:
- L38: `test_download_from_ftp_success` → `test_download_from_cloud_success` にリネーム
- L39: patch先 `BackcastPro.api.ftp_client.FTPClient` を削除、GDriveClient のmockに変更
- L127-128, L175: `_download_from_ftp` へのpatch → `_download_from_cloud` に修正

`tests/test_db_stocks_info.py`:
- L33: `test_download_from_ftp_success` → `test_download_from_cloud_success` にリネーム
- L35: patch先を GDriveClient のmockに変更
- L49-72: `test_download_from_ftp_failure_connection`, `test_download_from_ftp_not_configured` → FTP固有テストは削除、Google Drive失敗ケースのテストに書き換え

### 7. `.env`
FTP設定セクション(L27-33)を削除：
```
# FTP設定 (BackcastPro Data Sync)
BACKCASTPRO_FTP_HOST=...
BACKCASTPRO_FTP_PORT=...
BACKCASTPRO_FTP_USER=...
BACKCASTPRO_FTP_PASSWORD=...
```

### 8. `.github/workflows/update-stocks-price.yml`
- L32: `ftp_client` のimportチェック行を削除
- L40-42: FTP環境変数の設定を削除

### 9. GitHub Secrets のクリーンアップ
リポジトリの Settings > Secrets から以下を削除:
- `BACKCASTPRO_FTP_HOST`
- `BACKCASTPRO_FTP_USER`
- `BACKCASTPRO_FTP_PASSWORD`

### 10. ドキュメント
- `docs/troubleshooting.md` — FTPダウンロード失敗セクション(L158-165、閉じ```を含む)を削除
- `docs/developer-guide.md` — FTP設定(L71-75)、ftp_client.pyの記述(L101)、FTPフォールバック説明(L136-139)、テストファイル記述(L290)を削除
- `docs/tutorial.md` — L110のFTP言及を削除（「Google DriveまたはFTP」→「Google Drive」）

## 検証
- `uv run python -c "from BackcastPro.api.db_stocks_daily import StocksDailyDB; print('OK')"` でimportエラーがないか確認
- `uv run python -c "from BackcastPro.api.db_stocks_board import StocksBoardDB; print('OK')"` 同上
- `uv run python -c "from BackcastPro.api.db_stocks_info import StocksInfoDB; print('OK')"` 同上
- `uv run pytest tests/test_db_stocks_daily.py tests/test_db_stocks_info.py` でテストが通ることを確認
- `grep -ri ftp src/ tests/ docs/ .github/` でFTP参照が残っていないことを確認（docs/plans/ は除外）
