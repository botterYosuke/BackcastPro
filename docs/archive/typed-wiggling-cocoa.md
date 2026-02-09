# Cloud Run Job で夜間株価アップロード — 簡素化計画

## Context

`shimmering-roaming-pillow.md` は Cloud Run Job + Google Drive 直接アップロード (`GDriveUploader`) を提案している。
ユーザーは Cloud Run Job + Google Drive を維持しつつ、よりシンプルな実装を求めている。

**核心的な問題**: 現計画は `GDriveUploader` という新クラスで Google Drive API を直接叩く設計。
しかし既存の `GDriveClient` は Cloud Run proxy 経由の HTTP リクエストでダウンロードしている。
**同じパターンでアップロードも実現できる** — proxy に POST エンドポイントを追加するだけ。

---

## 現計画 vs 簡素化版の比較

| | 現計画 | 簡素化版 |
|---|---|---|
| 新規ファイル | 4 (`cloud-job/` 内) | 2 (Dockerfile + requirements.txt) |
| 新規クラス | `GDriveUploader` (~80行) | なし (既存 `GDriveClient` に ~15行追加) |
| Job の依存 | `google-api-python-client` + `google-auth` | `requests` のみ (既存) |
| Job 用シークレット | 5 (API keys + GOOGLE_SERVICE_ACCOUNT_JSON) | 4 (API keys + UPLOAD_API_KEY) |
| gcloud コマンド | 5 ステップ | 3 ステップ |
| Google Drive API 知識 | 必要 (フォルダ検索、ファイル作成/更新) | 不要 (proxy が吸収) |

---

## 簡素化のポイント (2つ)

### 1. アップロードを既存 Cloud Run proxy 経由にする

現在の構成:
```
download: update_stocks_price.py → (直接なし)
          GDriveClient → HTTP GET → Cloud Run proxy → Google Drive API → ファイル
```

現計画のアップロード:
```
upload:   update_stocks_price.py → GDriveUploader → Google Drive API → ファイル
          (新クラス、Google Drive SDK 直接利用、サービスアカウントJSON必要)
```

**簡素化版のアップロード:**
```
upload:   update_stocks_price.py → GDriveClient → HTTP POST → Cloud Run proxy → Google Drive API → ファイル
          (既存クラスに upload_file() 追加、HTTP POST するだけ)
```

ダウンロードと完全に対称なパターン。Job 側に Google Drive SDK 不要。

### 2. `gcloud run jobs deploy --source` で3ステップを1つに

現計画:
```bash
# Step 1: Artifact Registry 作成
gcloud artifacts repositories create backcastpro ...
# Step 2: イメージビルド & プッシュ
gcloud builds submit --tag asia-northeast1-docker.pkg.dev/... -f cloud-job/Dockerfile .
# Step 3: Job 作成
gcloud run jobs create update-stocks-price --image=asia-northeast1-docker.pkg.dev/...
```

**簡素化版:**
```bash
# 1コマンドで Artifact Registry 自動作成 + ビルド + Job 作成
gcloud run jobs deploy update-stocks-price \
  --source . \
  --dockerfile=cloud-job/Dockerfile \
  --region=asia-northeast1 \
  --task-timeout=3600 \
  --max-retries=1 \
  --memory=2Gi \
  --set-secrets="JQUANTS_API_KEY=JQUANTS_API_KEY:latest,eAPI_URL=eAPI_URL:latest,eAPI_USER_ID=eAPI_USER_ID:latest,eAPI_PASSWORD=eAPI_PASSWORD:latest" \
  --set-env-vars="BACKCASTPRO_CACHE_DIR=/tmp/backcastpro_cache,BACKCASTPRO_GDRIVE_API_URL=https://backcastpro-341714433786.asia-northeast1.run.app,UPLOAD_API_KEY=<key>"
```

---

## 変更ファイル一覧

| ファイル | 操作 | 変更量 |
|---------|------|--------|
| `cloud-run/main.py` | **編集** — POST アップロードエンドポイント追加 | +30行 |
| `src/BackcastPro/api/gdrive_client.py` | **編集** — `upload_file()` / `upload_stocks_daily()` 追加 | +15行 |
| `tasks/update_stocks_price.py` → `cloud-job/update_stocks_price.py` | **移動+編集** — `upload_to_ftp()` → `upload_to_cloud()` 置換 | ±20行 |
| `cloud-job/Dockerfile` | **新規作成** | 8行 |
| `cloud-job/requirements.txt` | **新規作成** | 6行 |

---

## Step 1: `cloud-run/main.py` に POST アップロード追加

### 1a. スコープを `drive.readonly` → `drive` に変更 (L103)

```python
# Before:
scopes = ["https://www.googleapis.com/auth/drive.readonly"]
# After:
scopes = ["https://www.googleapis.com/auth/drive"]
```

**前提**: Google Drive 共有フォルダでサービスアカウントに「編集者」権限が必要。

### 1b. `GoogleDriveProxy` に `upload_file()` メソッド追加

```python
def upload_file(self, folder_id: str, filename: str, data: bytes) -> str:
    """Upload or update a file in a folder. Returns file ID."""
    from googleapiclient.http import MediaInMemoryUpload

    existing_id = self.find_file(folder_id, filename)
    media = MediaInMemoryUpload(data, mimetype="application/octet-stream")

    if existing_id:
        result = self.service.files().update(
            fileId=existing_id, media_body=media
        ).execute()
        return result["id"]

    result = self.service.files().create(
        body={"name": filename, "parents": [folder_id]},
        media_body=media, fields="id"
    ).execute()
    return result["id"]
```

### 1c. POST ルート追加

```python
from flask import request as flask_request

@app.route("/jp/<path:file_path>", methods=["POST"])
def upload_handler(file_path: str):
    expected_key = os.environ.get("UPLOAD_API_KEY")
    if expected_key and flask_request.headers.get("X-API-Key") != expected_key:
        return "Unauthorized", 401

    if not ALLOWED_PATHS.match(file_path):
        return "Not Found", 404

    proxy = _get_proxy("jp")
    parts = file_path.split("/")
    if len(parts) != 2:
        return "Bad Request", 400

    subfolder_name, filename = parts
    folder_id = proxy.find_subfolder(subfolder_name)
    if not folder_id:
        return "Subfolder not found", 404

    data = flask_request.get_data()
    file_id = proxy.upload_file(folder_id, filename, data)
    logger.info("Uploaded: %s (file_id=%s, size=%d)", file_path, file_id, len(data))
    return {"file_id": file_id}, 200
```

### 1d. 既存 GET ルートに明示的に methods 指定

```python
@app.route("/jp/<path:file_path>", methods=["GET"])
def download_file(file_path: str):
    ...
```

---

## Step 2: `gdrive_client.py` に upload メソッド追加

既存の `GDriveClient` にダウンロードと対称なアップロードメソッドを追加:

```python
def upload_file(self, remote_path: str, local_path: str) -> bool:
    """Cloud Run API経由でファイルをアップロード"""
    url = f"{self.config.api_base_url.rstrip('/')}/jp/{remote_path}"
    api_key = os.environ.get("UPLOAD_API_KEY", "")

    try:
        logger.info(f"アップロード開始: {local_path} -> {remote_path}")
        with open(local_path, 'rb') as f:
            resp = requests.post(
                url, data=f,
                headers={"X-API-Key": api_key},
                timeout=(10, 300),
            )
        resp.raise_for_status()
        logger.info(f"アップロード完了: {remote_path}")
        return True
    except Exception as e:
        logger.warning(f"アップロード失敗: {e}")
        return False

def upload_stocks_daily(self, code: str, local_path: str) -> bool:
    return self.upload_file(f"stocks_daily/{code}.duckdb", local_path)
```

---

## Step 3: `tasks/update_stocks_price.py` → `cloud-job/update_stocks_price.py` に移動+編集

スクリプトを `cloud-job/` に移動し、Cloud Run Job の専用ディレクトリにまとめる。

### 3a. `upload_to_ftp()` → `upload_to_cloud()` に置換

```python
def upload_to_cloud(modified_codes: list[str], dry_run: bool = False) -> dict:
    from BackcastPro.api.gdrive_client import GDriveClient

    results = {'success': [], 'failed': []}
    if dry_run:
        logger.info("dry-run モード: アップロードをスキップ")
        results['success'] = modified_codes
        return results
    if not modified_codes:
        logger.info("アップロード対象ファイルなし")
        return results

    client = GDriveClient()
    if not client.config.is_configured():
        logger.error("BACKCASTPRO_GDRIVE_API_URL not configured")
        for code in modified_codes:
            results['failed'].append((code, "API URL not configured"))
        return results

    cache_dir = os.environ.get('BACKCASTPRO_CACHE_DIR', '.')
    for code in modified_codes:
        local_path = os.path.join(cache_dir, 'stocks_daily', f'{code}.duckdb')
        if not os.path.exists(local_path):
            results['failed'].append((code, "File not found"))
            continue
        if client.upload_stocks_daily(code, local_path):
            results['success'].append(code)
        else:
            results['failed'].append((code, "Upload failed"))

    return results
```

### 3b. `main()` 内の呼び出し変更

```python
# Before:
ftp_results = upload_to_ftp(modified_codes, dry_run=args.dry_run)
summary.ftp_uploaded = len(ftp_results['success'])
summary.ftp_failed = len(ftp_results['failed'])

# After:
upload_results = upload_to_cloud(modified_codes, dry_run=args.dry_run)
summary.uploaded = len(upload_results['success'])
summary.upload_failed = len(upload_results['failed'])
```

### 3c. `UpdateSummary` / logging / docstring の FTP → Cloud 置換

現計画の 3c, 3d, 3e と同じ。

---

## Step 4: `cloud-job/` 作成 (簡素化版)

### Dockerfile (google-api-python-client 不要)

```dockerfile
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=True
ENV PYTHONPATH=/app/src
WORKDIR /app

COPY cloud-job/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/BackcastPro/ /app/src/BackcastPro/
COPY src/trading_data/ /app/src/trading_data/
COPY cloud-job/update_stocks_price.py /app/update_stocks_price.py

CMD ["python", "/app/update_stocks_price.py"]
```

### requirements.txt (現計画より軽量)

```
pandas>=1.3.0
numpy>=1.20.0
duckdb>=0.9.0
python-dotenv>=0.19.0
requests>=2.25.0
yfinance>=0.2.0
```

**現計画との差**: `google-api-python-client` と `google-auth` が不要（proxy 経由なので）。

---

## Step 5: デプロイ

### 5a. Secret Manager (API キーのみ、現計画より1つ少ない)

```bash
echo -n "$JQUANTS_API_KEY" | gcloud secrets create JQUANTS_API_KEY --data-file=-
echo -n "$eAPI_URL" | gcloud secrets create eAPI_URL --data-file=-
echo -n "$eAPI_USER_ID" | gcloud secrets create eAPI_USER_ID --data-file=-
echo -n "$eAPI_PASSWORD" | gcloud secrets create eAPI_PASSWORD --data-file=-
```

`GOOGLE_SERVICE_ACCOUNT_JSON` は Job 側では不要（proxy が Google Drive API を担当）。

### 5b. Cloud Run Job デプロイ (1コマンド)

```bash
gcloud run jobs deploy update-stocks-price \
  --source . \
  --dockerfile=cloud-job/Dockerfile \
  --region=asia-northeast1 \
  --task-timeout=3600 \
  --max-retries=1 \
  --memory=2Gi \
  --cpu=1 \
  --set-secrets="JQUANTS_API_KEY=JQUANTS_API_KEY:latest,eAPI_URL=eAPI_URL:latest,eAPI_USER_ID=eAPI_USER_ID:latest,eAPI_PASSWORD=eAPI_PASSWORD:latest" \
  --set-env-vars="BACKCASTPRO_CACHE_DIR=/tmp/backcastpro_cache,BACKCASTPRO_GDRIVE_API_URL=https://backcastpro-341714433786.asia-northeast1.run.app,UPLOAD_API_KEY=<生成したキー>"
```

### 5c. Cloud Run Service 再デプロイ (スコープ変更 + UPLOAD_API_KEY 追加)

```bash
cd cloud-run
gcloud run deploy backcastpro-proxy \
  --source . \
  --region=asia-northeast1 \
  --set-env-vars="UPLOAD_API_KEY=<同じキー>"
```

### 5d. Cloud Scheduler (現計画と同じ)

```bash
gcloud scheduler jobs create http update-stocks-price-nightly \
  --location=asia-northeast1 \
  --schedule="30 19 * * 1-5" \
  --time-zone="Asia/Tokyo" \
  --uri="https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/backcastpro-341714433786/jobs/update-stocks-price:run" \
  --http-method=POST \
  --oauth-service-account-email=<SERVICE_ACCOUNT>@<PROJECT>.iam.gserviceaccount.com
```

---

## 前提条件

- Google Drive 共有フォルダでサービスアカウントに**編集者**権限を付与する
  （現在は閲覧者のみの可能性あり）

---

## 検証手順

1. **Cloud Run proxy ローカルテスト**: `cloud-run/main.py` の POST エンドポイントを単体テスト
2. **proxy 再デプロイ → curl で POST テスト**:
   ```bash
   curl -X POST \
     -H "X-API-Key: <key>" \
     --data-binary @test.duckdb \
     https://backcastpro-341714433786.asia-northeast1.run.app/jp/stocks_daily/9999.duckdb
   ```
3. **ローカルスクリプト実行**: `python cloud-job/update_stocks_price.py --codes 7203 --dry-run`
4. **ローカル実体アップロード**: `python cloud-job/update_stocks_price.py --codes 7203`
5. **ダウンロード確認**: `curl https://backcastpro-341714433786.asia-northeast1.run.app/jp/stocks_daily/7203.duckdb -o test.duckdb`
6. **Cloud Run Job 手動実行**: `gcloud run jobs execute update-stocks-price --args="--codes,7203,8306,--days,3"`
7. **Cloud Scheduler**: 翌営業日に実行履歴を確認
