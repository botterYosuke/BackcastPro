# Cloud Run デプロイ作業依頼

## 概要

BackcastPro プロジェクトで以下2つのデプロイを行ってください。
コードは全て完成済み。gcloud CLI でのデプロイ作業のみです。

1. **Cloud Run Service 再デプロイ** — 既存サービスに POST アップロード機能を追加
2. **Cloud Run Job 新規デプロイ** — 夜間株価取得バッチジョブ

---

## 環境情報

| 項目 | 値 |
|------|-----|
| GCP プロジェクト ID | `carbide-booth-486907-a3` |
| プロジェクト番号 | `341714433786` |
| リージョン | `asia-northeast1` |
| gcloud 認証アカウント | `sasaicco@gmail.com` (ログイン済み) |
| gcloud プロジェクト | 設定済み (`carbide-booth-486907-a3`) |
| OS | Windows (gcloud は `gcloud.cmd` を使うこと) |
| 作業ディレクトリ | `C:\Users\sasai\Documents\BackcastPro` |

### Secret Manager (登録済み・IAM 設定済み)

以下5つのシークレットが登録済み。サービスアカウント `341714433786-compute@developer.gserviceaccount.com` に全シークレットへの `secretAccessor` ロール付与済み。

- `JQUANTS_API_KEY`
- `eAPI_URL`
- `eAPI_USER_ID`
- `eAPI_PASSWORD`
- `UPLOAD_API_KEY`

### 既存のサービスアカウント

| SA | 用途 |
|----|------|
| `341714433786-compute@developer.gserviceaccount.com` | Cloud Run デフォルト (Service/Job 両方) |
| `gdrive-proxy-sa@carbide-booth-486907-a3.iam.gserviceaccount.com` | Google Drive プロキシ用 |

---

## 作業1: Cloud Run Service 再デプロイ

既存の Cloud Run Service `backcastpro` を再デプロイします。
POST アップロードエンドポイントと `UPLOAD_API_KEY` による認証が追加されています。

- 既存 URL: `https://backcastpro-341714433786.asia-northeast1.run.app`
- ソースディレクトリ: `cloud-run/` (Dockerfile, main.py, requirements.txt)
- Dockerfile のビルドコンテキストは `cloud-run/` 自体

### コマンド

```bash
cd C:\Users\sasai\Documents\BackcastPro\cloud-run

gcloud.cmd run deploy backcastpro ^
  --source . ^
  --region=asia-northeast1 ^
  --set-secrets="UPLOAD_API_KEY=UPLOAD_API_KEY:latest,GOOGLE_SERVICE_ACCOUNT_JSON=GOOGLE_SERVICE_ACCOUNT_JSON:latest" ^
  --set-env-vars="GOOGLE_DRIVE_ROOT_FOLDER_ID=1LxXZ7dZv4oXlYyXH6OZtt_0yVbwtyiF4"
```

### 注意事項

- `GOOGLE_SERVICE_ACCOUNT_JSON` が Secret Manager に存在しない場合はエラーになる。その場合は `--set-secrets="UPLOAD_API_KEY=UPLOAD_API_KEY:latest"` のみにする
- `--allow-unauthenticated` を聞かれたら **Yes**（公開 API）
- 既存の環境変数・シークレット設定がリセットされる可能性がある。必要に応じて `gcloud.cmd run services describe backcastpro --region=asia-northeast1 --format=yaml` で現在の設定を事前確認すること

### 確認方法

```bash
curl https://backcastpro-341714433786.asia-northeast1.run.app/
```
→ `OK` が返れば成功

---

## 作業2: Cloud Run Job 新規デプロイ

夜間株価取得スクリプトを Cloud Run Job `update-stocks-price` としてデプロイします。

- ソースディレクトリ: プロジェクトルート全体
- Dockerfile: `cloud-job/Dockerfile` (ビルドコンテキストはプロジェクトルート)
- `.gcloudignore` でビルドに不要なファイルは除外済み

### 方法A: 1コマンド (--source + --dockerfile)

```bash
cd C:\Users\sasai\Documents\BackcastPro

gcloud.cmd run jobs deploy update-stocks-price ^
  --source . ^
  --dockerfile=cloud-job/Dockerfile ^
  --region=asia-northeast1 ^
  --task-timeout=3600 ^
  --max-retries=1 ^
  --memory=2Gi ^
  --cpu=1 ^
  --set-secrets="JQUANTS_API_KEY=JQUANTS_API_KEY:latest,eAPI_URL=eAPI_URL:latest,eAPI_USER_ID=eAPI_USER_ID:latest,eAPI_PASSWORD=eAPI_PASSWORD:latest,UPLOAD_API_KEY=UPLOAD_API_KEY:latest" ^
  --set-env-vars="BACKCASTPRO_CACHE_DIR=/tmp/backcastpro_cache,BACKCASTPRO_GDRIVE_API_URL=https://backcastpro-341714433786.asia-northeast1.run.app"
```

### 方法B: 2ステップ (方法A が `--dockerfile` 非対応で失敗した場合)

```bash
cd C:\Users\sasai\Documents\BackcastPro

# B-0. Artifact Registry リポジトリ作成 (初回のみ)
gcloud.cmd artifacts repositories create cloud-run-source-deploy ^
  --repository-format=docker ^
  --location=asia-northeast1

# B-1. コンテナイメージのビルド & プッシュ
gcloud.cmd builds submit ^
  --tag asia-northeast1-docker.pkg.dev/carbide-booth-486907-a3/cloud-run-source-deploy/update-stocks-price:latest ^
  -f cloud-job/Dockerfile .

# B-2. Cloud Run Job 作成
gcloud.cmd run jobs create update-stocks-price ^
  --image=asia-northeast1-docker.pkg.dev/carbide-booth-486907-a3/cloud-run-source-deploy/update-stocks-price:latest ^
  --region=asia-northeast1 ^
  --task-timeout=3600 ^
  --max-retries=1 ^
  --memory=2Gi ^
  --cpu=1 ^
  --set-secrets="JQUANTS_API_KEY=JQUANTS_API_KEY:latest,eAPI_URL=eAPI_URL:latest,eAPI_USER_ID=eAPI_USER_ID:latest,eAPI_PASSWORD=eAPI_PASSWORD:latest,UPLOAD_API_KEY=UPLOAD_API_KEY:latest" ^
  --set-env-vars="BACKCASTPRO_CACHE_DIR=/tmp/backcastpro_cache,BACKCASTPRO_GDRIVE_API_URL=https://backcastpro-341714433786.asia-northeast1.run.app"
```

### 確認方法

dry-run モードで手動実行:
```bash
gcloud.cmd run jobs execute update-stocks-price ^
  --region=asia-northeast1 ^
  --args="--codes,7203,--days,3,--dry-run"
```

ログ確認:
```bash
gcloud.cmd run jobs executions list --job=update-stocks-price --region=asia-northeast1
```
→ ジョブが正常に完了 (exit code 0) すれば成功

---

## トラブルシューティング

### Cloud Build API が無効
```bash
gcloud.cmd services enable cloudbuild.googleapis.com
gcloud.cmd services enable artifactregistry.googleapis.com
```

### Artifact Registry リポジトリが存在しない
方法 B-0 のコマンドで作成。既に存在する場合は ALREADY_EXISTS エラーが出るが無害。

### シークレットが見つからないエラー
```bash
gcloud.cmd secrets list
```
で一覧確認。名前が一致するか確認すること。
