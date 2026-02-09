# Cloud Run proxy アップロード廃止 → Docker マウントフォルダの DuckDB 直接書き込み

**ステータス: 実装済み**

## 背景

`cloud-job/update_stocks_price.py` は、株価データを DuckDB に保存した後、Cloud Run proxy 経由で Google Drive にアップロードしていた。
Google Drive へのアップロードを廃止し、Docker でマウントしたフォルダ内の DuckDB ファイルに直接保存する方式に変更した。

DuckDB への保存は元々 `db_stocks_daily.save_stock_prices()` が環境変数 `STOCKDATA_CACHE_DIR` を参照して動作しているため、アップロード関連コードの削除と Dockerfile のボリュームマウント対応のみで実現。

## 変更後の動作

```
株価データソース (Tachibana / Stooq / J-Quants)
        ↓ 取得・マージ
    DuckDB に保存
    (STOCKDATA_CACHE_DIR/stocks_daily/{code}.duckdb)
```

Docker 実行時に `-v` でホスト側ディレクトリをマウントすることで、DuckDB ファイルがホスト側に永続化される。

```bash
docker run -v /host/duckdb-dir:/data backcastpro-updater --codes 7203 --days 3
# → /host/duckdb-dir/stocks_daily/7203.duckdb に保存される
```

## 変更したファイル

| ファイル | 変更内容 |
|---|---|
| `cloud-job/update_stocks_price.py` | `upload_to_cloud()` 関数削除、`--dry-run` 引数削除、`UpdateSummary` のアップロード関連フィールド削除、docstring・サマリー出力の更新 |
| `cloud-job/Dockerfile` | `ENV STOCKDATA_CACHE_DIR=/data` 追加（ボリュームマウントポイント） |
| `tests/test_update_stocks_price.py` | `TestUploadToCloud` クラス削除、`--dry-run` 関連テスト削除、`TestMain` のアップロードモック削除 |
| `cloud-job/requirements.txt` | 変更なし（`requests` は Stooq/J-Quants/Tachibana の API 呼び出しで引き続き必要） |

## 未対応事項

- **GitHub Actions ワークフロー** (`deploy-cloud-run-job.yml`): Cloud Run Jobs でボリュームマウントを使う場合、`gcloud run jobs update` に `--add-volume` / `--add-volume-mount` の設定が必要。現在のワークフローには未反映。
- **ドキュメント** (`docs/cloud-run-updater.md`): `--dry-run` の使用例、CloudRunClient 経由のアップロード説明、Google Drive 参照が旧仕様のまま残っている。

## 検証手順

1. テスト: `python -m pytest tests/test_update_stocks_price.py -v`（37 テスト全 PASSED 確認済み）
2. Docker ビルド: `docker build -f cloud-job/Dockerfile -t backcastpro-updater .`
3. 動作確認: `docker run -v <host-dir>:/data backcastpro-updater --codes 7203 --days 3`
   - `/data/stocks_daily/7203.duckdb` にデータが保存されることを確認
