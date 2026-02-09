# Cloud Run API サーバー側実装計画 (Google Drive Proxy)

## Context
本ドキュメントは [FTP download to GDrive migration](migration_ftp_to_gdrive.md) のサーバー側実装計画である。
クライアント側 (`gdrive_client.py`) が `GET {API_BASE_URL}/jp/{path}` にリクエストを送ることを想定し、サーバー側はGoogle Drive API経由でファイルを見つけ、ストリーム返却するプロキシAPIを構築する。

- フレームワーク: Flask + gunicorn
- 認証: サービスアカウントJSONキー（環境変数 `GOOGLE_SERVICE_ACCOUNT_JSON` で渡す）
- Google Driveフォルダ: 環境変数 `GOOGLE_DRIVE_ROOT_FOLDER_ID` で指定
- デプロイ先: Google Cloud Run (Region: asia-northeast1)
- デプロイ方法: GitHubリポジトリ接続による自動デプロイ

## ディレクトリ構造
プロジェクトルート直下の `cloudrun/` ディレクトリに配置する。

```
cloudrun/
├── main.py              # Flaskアプリ本体
├── requirements.txt     # Python依存関係
├── Dockerfile           # Cloud Runデプロイ用
├── .dockerignore        # ビルド対象外の設定
├── .env.example         # 環境変数テンプレート
└── deploy.sh            # デプロイ用スクリプト（オプション）
```

## `cloudrun/main.py` 設計

```python
import os
import json
import logging
import re
import io
from flask import Flask, Response, abort
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

app = Flask(__name__)

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# パスバリデーション (セキュリティ)
ALLOWED_PATHS = re.compile(
    r"^(stocks_daily/\d+\.duckdb|stocks_board/\d+\.duckdb|listed_info\.duckdb)$"
)

# Google Drive 設定
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

class GoogleDriveProxy:
    def __init__(self):
        self.root_folder_id = os.environ.get('GOOGLE_DRIVE_ROOT_FOLDER_ID')
        if not self.root_folder_id:
            raise ValueError("GOOGLE_DRIVE_ROOT_FOLDER_ID not set")
        self.service = self._get_service()
        self._folder_cache = {}

    def _get_service(self):
        creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        if not creds_json:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON not set")
        
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        return build('drive', 'v3', credentials=creds)

    def find_subfolder(self, name):
        if name in self._folder_cache:
            return self._folder_cache[name]

        query = f"'{self.root_folder_id}' in parents and name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = self.service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if not files:
            return None
        
        folder_id = files[0]['id']
        self._folder_cache[name] = folder_id
        return folder_id

    def find_file(self, folder_id, filename):
        query = f"'{folder_id}' in parents and name='{filename}' and trashed=false"
        results = self.service.files().list(q=query, fields="files(id, name, size)").execute()
        files = results.get('files', [])
        
        if not files:
            return None
        return files[0]

    def stream_file(self, file_id):
        request = self.service.files().get_media(fileId=file_id)
        
        def generate():
            fh = io.BytesIO()
            # 1MB単位でチャンクダウンロード
            downloader = MediaIoBaseDownload(fh, request, chunksize=1024*1024)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                fh.seek(0)
                yield fh.read()
                fh.seek(0)
                fh.truncate()
        
        return Response(generate(), mimetype='application/octet-stream')

drive_proxy = None

@app.before_request
def initialize_service():
    global drive_proxy
    if drive_proxy is None:
        try:
            drive_proxy = GoogleDriveProxy()
        except Exception as e:
            logger.error(f"Failed to initialize Drive service: {e}")

@app.route("/")
def health():
    return "OK", 200

@app.route("/jp/<path:file_path>")
def download_file(file_path):
    # バリデーション
    if not ALLOWED_PATHS.match(file_path):
        return abort(404, description="Invalid path or file not allowed")

    global drive_proxy
    if not drive_proxy:
        return abort(500, description="Drive Service not initialized")

    parts = file_path.split('/')
    
    if len(parts) == 1:
        target_file = drive_proxy.find_file(drive_proxy.root_folder_id, parts[0])
    elif len(parts) == 2:
        folder_id = drive_proxy.find_subfolder(parts[0])
        if not folder_id:
            return abort(404, description="Folder not found")
        target_file = drive_proxy.find_file(folder_id, parts[1])
    else:
        return abort(400, description="Invalid path format")

    if not target_file:
        return abort(404, description="File not found")

    response = drive_proxy.stream_file(target_file['id'])
    response.headers["Content-Disposition"] = f"attachment; filename={parts[-1]}"
    return response

@app.errorhandler(Exception)
def handle_error(e):
    if isinstance(e, HttpError):
        if e.resp.status == 404:
            return "File not found (Drive API)", 404
        logger.error(f"Drive API error: {e}")
        return "Google Drive API error", 503
    logger.error(f"Internal error: {e}")
    return "Internal server error", 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
```

## `cloudrun/requirements.txt`
```
flask>=3.0
gunicorn>=22.0
google-api-python-client>=2.100
google-auth>=2.20
```

## `cloudrun/Dockerfile`
```dockerfile
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=True
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
```

## `cloudrun/.dockerignore`
```
__pycache__
*.pyc
.env
.git
sa-key.json
```

## デプロイ設定 (Cloud Run / Cloud Build)
GitHubリポジトリ接続による自動デプロイを使用する場合：

1. **Dockerfile パス**: 
   Cloud Run のビルド設定で、Dockerfile のパスを `cloudrun/Dockerfile`、ソースのコンテキストディレクトリを `cloudrun/` に設定する。
2. **環境変数**:
   - `GOOGLE_SERVICE_ACCOUNT_JSON`: サービスアカウントのJSONキー文字列
   - `GOOGLE_DRIVE_ROOT_FOLDER_ID`: `1LxXZ7dZv4oXlYyXH6OZtt_0yVbwtyiF4`

## 検証項目
- [ ] ヘルスチェック `/` が OK を返すか
- [ ] `ALLOWED_PATHS` 以外のパスで 404 が返るか
- [ ] `listed_info.duckdb` が正しくダウンロードできるか
- [ ] 巨大な .duckdb ファイルでもメモリ使用量が高騰せずストリーム返却されるか
- [ ] サービスアカウントが対象フォルダの「閲覧者」権限を持っているか
