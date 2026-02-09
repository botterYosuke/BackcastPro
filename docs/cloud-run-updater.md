# Cloud Run Jobによる株価データ更新

BackcastProは、夜間にCloud Run Jobを使用して株価データを自動更新する仕組みを備えています。

## アーキテクチャ

データの更新プロセスは以下の通りです：

1. **Cloud Scheduler** が毎晩定刻（例: 19:30 JST）に **Cloud Run Job** をトリガーします。
2. **Cloud Run Job** (`update_stocks_price.py`) が実行されます。
   - J-Quants APIなどから最新の株価データを取得します。
   - 取得したデータをDuckDBファイルとして生成・更新します。
3. **Cloud Run Proxy** 経由で **Google Drive** にアップロードします。
   - Jobは `GDriveClient` を使用し、Cloud Run Proxyのエンドポイントに対して `POST` リクエストを送信します。
   - Proxyは受け取ったデータをGoogle Driveの所定のフォルダ（`jp/stocks_daily` など）に保存します。

## 構成要素

### 1. Cloud Run Job (`update_stocks_price`)
- **ソース**: `cloud-job/`
- **役割**: データのダウンロード、加工、アップロード
- **認証**: Secret ManagerからAPIキーなどを取得

### 2. Cloud Run Proxy (`backcastpro-proxy`)
- **ソース**: `cloud-run/`
- **役割**: Google Driveへのアクセス（ダウンロード/アップロード）の中継
- **認証**: `UPLOAD_API_KEY` による簡易認証（Job -> Proxy間）

## デプロイ手順

### 前提条件
Google Cloud SDK (`gcloud`) がインストール・設定されていること。

必要なSecretがSecret Managerに登録されていること：
- `JQUANTS_API_KEY`
- `eAPI_URL`
- `eAPI_USER_ID`
- `eAPI_PASSWORD`
- `UPLOAD_API_KEY` (ProxyとJobで共有)

### 1. Cloud Run Job のデプロイ

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
  --set-env-vars="BACKCASTPRO_CACHE_DIR=/tmp/backcastpro_cache,BACKCASTPRO_GDRIVE_API_URL=https://YOUR-PROXY-URL.run.app,UPLOAD_API_KEY=YOUR_UPLOAD_KEY"
```

### 2. Cloud Scheduler の設定

```bash
gcloud scheduler jobs create http update-stocks-price-nightly \
  --location=asia-northeast1 \
  --schedule="30 19 * * 1-5" \
  --time-zone="Asia/Tokyo" \
  --uri="https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/YOUR-PROJECT/jobs/update-stocks-price:run" \
  --http-method=POST \
  --oauth-service-account-email=YOUR-SERVICE-ACCOUNT-EMAIL
```

## 運用・監視

- **ログ確認**: Cloud ConsoleのCloud Run Jobsセクションからログを確認できます。
- **データ確認**: 更新されたデータは、ローカル環境で `GDriveClient` を通じてダウンロードするか、またはGoogle Driveを直接確認することで検証できます。
