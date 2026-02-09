# update_stocks_price.py を Cloud Run Job で実行する

## Context

`tasks/update_stocks_price.py` は夜間に株価データを複数ソース (Tachibana → Stooq → J-Quants) から取得し、DuckDB に保存後 FTP アップロードするスクリプト。
これを Cloud Run Job としてコンテナ化し、Cloud Scheduler でスケジュール実行する。
既存の `cloud-run/` (Google Drive ダウンロードプロキシ Service) はそのまま維持する。

FTP アップロードは Google Drive アップロードに置き換える（FTP 廃止の方針に沿う）。

---

## 変更ファイル一覧

| ファイル | 操作 |
|---------|------|
| `cloud-job/Dockerfile` | **新規作成** |
| `cloud-job/requirements.txt` | **新規作成** |
| `cloud-job/.dockerignore` | **新規作成** |
| `cloud-job/.env.example` | **新規作成** |
| `src/BackcastPro/api/gdrive_client.py` | **編集** — `GDriveUploader` クラス追加 |
| `tasks/update_stocks_price.py` | **編集** — FTP → Google Drive 置換 + Cloud Run 対応 |

---

## Step 1: `cloud-job/` ディレクトリ作成

### Dockerfile
- ビルドコンテキストはプロジェクトルート (`docker build -f cloud-job/Dockerfile .`)
- `PYTHONPATH=/app/src` で `BackcastPro` と `trading_data` をインポート可能にする

```dockerfile
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=True
ENV PYTHONPATH=/app/src
WORKDIR /app

COPY cloud-job/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/BackcastPro/ /app/src/BackcastPro/
COPY src/trading_data/ /app/src/trading_data/
COPY tasks/update_stocks_price.py /app/tasks/update_stocks_price.py

CMD ["python", "/app/tasks/update_stocks_price.py"]
```

### requirements.txt
```
pandas>=1.3.0
numpy>=1.20.0
duckdb>=0.9.0
python-dotenv>=0.19.0
requests>=2.25.0
yfinance>=0.2.0
google-api-python-client>=2.100
google-auth>=2.20
```

### .dockerignore
```
__pycache__
*.pyc
.env
.git
*.duckdb
```

### .env.example
```
JQUANTS_API_KEY=
eAPI_URL=
eAPI_USER_ID=
eAPI_PASSWORD=
GOOGLE_SERVICE_ACCOUNT_JSON=
GOOGLE_DRIVE_ROOT_FOLDER_ID=1LxXZ7dZv4oXlYyXH6OZtt_0yVbwtyiF4
BACKCASTPRO_CACHE_DIR=/tmp/backcastpro_cache
```

---

## Step 2: `GDriveUploader` クラスを `gdrive_client.py` に追加

既存の `GDriveClient`（ダウンロード専用、Cloud Run プロキシ経由）はそのまま維持。
新たに Google Drive API 直接アップロード用の `GDriveUploader` クラスを追加する。

認証パターンは `cloud-run/main.py:100-115` の `_build_credentials()` を再利用。
フォルダ探索パターンは `cloud-run/main.py:37-76` の `find_subfolder` / `find_file` を再利用。

```python
class GDriveUploader:
    """Google Drive 直接アップロードクライアント（Cloud Run Job 用）"""

    def __init__(self):
        self.credentials = self._build_credentials()
        self.service = build("drive", "v3", credentials=self.credentials)
        self.root_folder_id = os.environ.get(
            "GOOGLE_DRIVE_ROOT_FOLDER_ID", "1LxXZ7dZv4oXlYyXH6OZtt_0yVbwtyiF4"
        )
        self._folder_cache: dict[str, str] = {}

    def _build_credentials(self):
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        scopes = ["https://www.googleapis.com/auth/drive"]  # read/write
        if sa_json:
            import json
            from google.oauth2 import service_account
            info = json.loads(sa_json)
            return service_account.Credentials.from_service_account_info(info, scopes=scopes)
        import google.auth
        credentials, _ = google.auth.default(scopes=scopes)
        return credentials

    def _find_subfolder(self, parent_id: str, name: str) -> str | None:
        # cloud-run/main.py の GoogleDriveProxy.find_subfolder と同パターン
        ...

    def _find_file(self, folder_id: str, filename: str) -> str | None:
        # cloud-run/main.py の GoogleDriveProxy.find_file と同パターン
        ...

    def upload_file(self, local_path: str, remote_subfolder: str, filename: str) -> bool:
        """ファイルをアップロード（既存ファイルがあれば上書き更新）"""
        # 1. root → "jp" サブフォルダを解決
        # 2. "jp" → remote_subfolder (e.g. "stocks_daily") を解決
        # 3. ファイルが既存なら update、なければ create
        ...

    def upload_stocks_daily(self, code: str, local_path: str) -> bool:
        return self.upload_file(local_path, "stocks_daily", f"{code}.duckdb")
```

**注意**: スコープは `drive`（read/write）。既存プロキシ Service は `drive.readonly` のまま。

---

## Step 3: `update_stocks_price.py` を編集

### 3a. `upload_to_ftp()` → `upload_to_gdrive()` に置換（L274-344）

```python
def upload_to_gdrive(modified_codes: list[str], dry_run: bool = False) -> dict:
    from BackcastPro.api.gdrive_client import GDriveUploader

    results = {'success': [], 'failed': []}
    if dry_run:
        logger.info("dry-run モード: Google Driveアップロードをスキップ")
        results['success'] = modified_codes
        return results
    if not modified_codes:
        logger.info("アップロード対象ファイルなし")
        return results

    uploader = GDriveUploader()
    cache_dir = os.environ.get('BACKCASTPRO_CACHE_DIR', '.')
    local_dir = os.path.join(cache_dir, 'stocks_daily')

    for code in modified_codes:
        local_path = os.path.join(local_dir, f"{code}.duckdb")
        if not os.path.exists(local_path):
            results['failed'].append((code, "File not found"))
            continue
        try:
            if uploader.upload_stocks_daily(code, local_path):
                results['success'].append(code)
            else:
                results['failed'].append((code, "Upload failed"))
        except Exception as e:
            logger.error(f"  Google Drive upload failed {code}: {e}")
            results['failed'].append((code, str(e)))

    return results
```

### 3b. `main()` 内の呼び出し変更（L460-464）

```python
# Before:
ftp_results = upload_to_ftp(modified_codes, dry_run=args.dry_run)
summary.ftp_uploaded = len(ftp_results['success'])
summary.ftp_failed = len(ftp_results['failed'])

# After:
gdrive_results = upload_to_gdrive(modified_codes, dry_run=args.dry_run)
summary.uploaded = len(gdrive_results['success'])
summary.upload_failed = len(gdrive_results['failed'])
```

### 3c. `UpdateSummary` フィールド名変更（L39-49）

`ftp_uploaded` → `uploaded`, `ftp_failed` → `upload_failed`

### 3d. `setup_logging()` を Cloud Run 対応に（L52-89）

Cloud Run Jobs では `CLOUD_RUN_JOB` 環境変数が自動設定される。
これを検出し、ファイルハンドラをスキップ（stdout のみ = Cloud Logging が自動取得）。

```python
def setup_logging() -> logging.Logger:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S'
    ))
    root_logger.addHandler(console_handler)

    # Cloud Run ではファイルハンドラ不要（stdout → Cloud Logging）
    if not os.environ.get('CLOUD_RUN_JOB'):
        cache_dir = os.environ.get('BACKCASTPRO_CACHE_DIR', '.')
        log_dir = os.path.join(cache_dir, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        # ... 既存の RotatingFileHandler 設定 ...
        root_logger.addHandler(file_handler)

    return logging.getLogger(__name__)
```

### 3e. docstring/help テキスト更新

- ファイル先頭のdocstring: "FTPアップロード" → "Google Driveアップロード"
- `--dry-run` のヘルプ: "FTPアップロードをスキップ" → "Google Driveアップロードをスキップ"
- サマリー出力の "FTPアップロード" → "Google Driveアップロード"

---

## Step 4: デプロイ手順（コードではなく CLI 操作）

### 4a. Artifact Registry リポジトリ作成

```bash
gcloud artifacts repositories create backcastpro \
  --repository-format=docker \
  --location=asia-northeast1 \
  --project=backcastpro-341714433786
```

### 4b. コンテナイメージのビルド & プッシュ

```bash
# プロジェクトルートから実行
gcloud builds submit \
  --tag asia-northeast1-docker.pkg.dev/backcastpro-341714433786/backcastpro/update-stocks-price:latest \
  -f cloud-job/Dockerfile .
```

### 4c. Secret Manager にシークレット作成

```bash
echo -n "$JQUANTS_API_KEY" | gcloud secrets create JQUANTS_API_KEY --data-file=-
echo -n "$eAPI_URL" | gcloud secrets create eAPI_URL --data-file=-
echo -n "$eAPI_USER_ID" | gcloud secrets create eAPI_USER_ID --data-file=-
echo -n "$eAPI_PASSWORD" | gcloud secrets create eAPI_PASSWORD --data-file=-
# GOOGLE_SERVICE_ACCOUNT_JSON は既存 Service と共有可
```

### 4d. Cloud Run Job 作成

```bash
gcloud run jobs create update-stocks-price \
  --image=asia-northeast1-docker.pkg.dev/backcastpro-341714433786/backcastpro/update-stocks-price:latest \
  --region=asia-northeast1 \
  --task-timeout=3600 \
  --max-retries=1 \
  --memory=2Gi \
  --cpu=1 \
  --set-secrets="JQUANTS_API_KEY=JQUANTS_API_KEY:latest,eAPI_URL=eAPI_URL:latest,eAPI_USER_ID=eAPI_USER_ID:latest,eAPI_PASSWORD=eAPI_PASSWORD:latest,GOOGLE_SERVICE_ACCOUNT_JSON=GOOGLE_SERVICE_ACCOUNT_JSON:latest" \
  --set-env-vars="BACKCASTPRO_CACHE_DIR=/tmp/backcastpro_cache,GOOGLE_DRIVE_ROOT_FOLDER_ID=1LxXZ7dZv4oXlYyXH6OZtt_0yVbwtyiF4"
```

### 4e. Cloud Scheduler 設定

```bash
gcloud scheduler jobs create http update-stocks-price-nightly \
  --location=asia-northeast1 \
  --schedule="30 19 * * 1-5" \
  --time-zone="Asia/Tokyo" \
  --uri="https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/backcastpro-341714433786/jobs/update-stocks-price:run" \
  --http-method=POST \
  --oauth-service-account-email=<SERVICE_ACCOUNT>@<PROJECT>.iam.gserviceaccount.com
```

平日 19:30 JST（J-Quants データ更新後）。

---

## 検証手順

1. **ローカル Docker テスト**
   ```bash
   docker build -f cloud-job/Dockerfile -t update-stocks-price .
   docker run --env-file cloud-job/.env update-stocks-price \
     python /app/tasks/update_stocks_price.py --codes 7203 --dry-run
   ```

2. **Cloud Run Job 手動実行（少数銘柄）**
   ```bash
   gcloud run jobs execute update-stocks-price \
     --args="--codes,7203,8306,--days,3"
   ```

3. **Google Drive 確認**: アップロード後、既存の Cloud Run Service プロキシ経由でダウンロードできることを確認
   ```
   curl https://backcastpro-341714433786.asia-northeast1.run.app/jp/stocks_daily/7203.duckdb -o test.duckdb
   ```

4. **Cloud Scheduler**: 翌営業日に実行履歴を確認
