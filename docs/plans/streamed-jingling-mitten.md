# mother.duckdb 統合DB ＋ GraphQL ランキングAPI

> **ステータス：実装完了（2026-02-28）**

---

## 背景・問題意識

現状、約4000銘柄が個別 `{code}.duckdb` に分かれており、
値上がり率ランキング等の全銘柄横断クエリが構造上不可能だった。

**パス:** `S:\jp\stocks_daily\{code}.duckdb`

### メリット

個別銘柄へのアクセスと、データ管理の柔軟性に特化した設計です。

| # | 観点 | 内容 |
| --- | --- | --- |
| 1 | **単一銘柄の取得が高速** | 対象ファイル1つを開くだけで済む。 |
| 2 | **障害の局所化** | 1ファイルが壊れても他銘柄に影響しない。 |
| 3 | **並列書き込みが容易** | 銘柄ごとにファイルが分離されているため、スレッド間でロック競合が起きにくい（`_save_to_cache_async` との相性が良い）。 |
| 4 | **オンデマンド取得** | `ensure_db_ready` が必要な銘柄のみをクラウドからダウンロード可能。 |
| 5 | **個別管理が簡単** | 特定銘柄のキャッシュだけを消去・再取得できる。 |
| 6 | **ファイルサイズが小さい** | 1銘柄分のデータなので軽量。配布・転送が容易。 |

---

### デメリット

全銘柄を横断して比較・集計するような「集合」としての操作において顕著な課題があります。

| # | 観点 | 内容 |
| --- | --- | --- |
| 1 | **クロス銘柄クエリが極めて遅い** | ランキング算出等のために約4,000ファイルを順次 `connect → query → close` する必要がある。 |
| 2 | **接続オーバーヘッドの累積** | DuckDB接続確立コストが4,000回発生し、I/O待ちが支配的になる。 |
| 3 | **SQL JOIN・集計が不可** | 全銘柄横断の `SELECT TOP 10 ...` のような単一クエリが物理的に書けない。 |
| 4 | **日付軸の取得が遅い** | 「特定日の全銘柄終値」を取得する場合も、4,000ファイルを走査する必要がある。 |
| 5 | **ファイルシステム（FS）負荷** | 4,000以上の小ファイルは、NTFS等のメタデータ管理コストを増大させる。 |
| 6 | **クラウド同期コスト** | 全銘柄の最新化において、4,000ファイルの個別確認・ダウンロードが必要になる。 |
| 7 | **横断インデックスの欠如** | 構造上、全銘柄を対象としたグローバルなインデックスを作成できない。 |

---

### 要約

**単一銘柄取得には最適だが、全銘柄比較には本質的に不向き：**
- ランキング算出 = 4,000回の `connect → query → close` = I/Oボトルネック
- DuckDB は単一ファイル内でのみ SQL JOIN・集計が有効
- 横断インデックスを作れない

### 解決策：二層構造

```
APIs → update_stocks_price.py
         ↓ fetch → upsert
       S:\jp\stocks_daily\mother.duckdb   ← 全銘柄統合ソース（新設）
         ↓ split（日次バッチ内）
       S:\jp\stocks_daily\{code}.duckdb   ← 単一銘柄取得用（既存・変更なし）

GraphQL query → cloud-run/main.py → mother.duckdb（on-the-fly SQL）
```

**設計の原則：**
- mother.duckdb が唯一の書き込み先。個別DBは母DBの派生物として自動生成される
- 単一銘柄の read パスは一切変えない（`get_stock_daily()` はそのまま動作）
- GraphQL は母DBに直接クエリ。ランキング計算はリクエスト時にSQLで行う（事前集計なし）

---

## 実装完了タスク

| # | タスク | ファイル | 状態 |
|---|--------|---------|------|
| 1 | 統合DB管理クラスの新規作成 | `src/BackcastPro/api/db_stocks_daily_mother.py` | ✅ |
| 2 | 夜間バッチの保存先を mother_db に変更 | `cloud-job/update_stocks_price.py` | ✅ |
| 3 | Cloud Run 依存パッケージの追加 | `cloud-run/requirements.txt` | ✅ |
| 4 | GraphQL API の追加 + ALLOWED_PATHS 修正 | `cloud-run/main.py` | ✅ |

---

## 実装詳細

### 1. `db_stocks_daily_mother` クラス
**ファイル：** `src/BackcastPro/api/db_stocks_daily_mother.py`

`db_stocks_daily` を継承し、**クラス変数2つを上書きするだけ**で動作する。

```python
class db_stocks_daily_mother(db_stocks_daily):
    _db_subdir   = None
    _db_filename = "stocks_daily/mother.duckdb"
```

**なぜこれだけで動くか：**
`db_manager._get_db_path()` のロジック（db_manager.py:347）は
`_db_subdir and code` が truthy のとき `{code}.duckdb`、
falsy のとき `_db_filename` を使う。`_db_subdir=None` にすることで
`get_db("7203")` でも常に同一の `mother.duckdb` を返す。

`save_stock_prices(code, df)` は内部でコード別にレコードを管理しているため、
複数銘柄を1ファイルに混在させても問題なし（Code カラムで分離）。

**`split_to_individual()` の設計ポイント：**
- `with self.get_db() as db:` を**ループ外で1回だけオープン**（4000回の open/close を回避）
- コードリスト取得も同じ接続内で実施（2回接続を1回に統合）
- `from_date=None` で全期間、文字列指定で差分のみ処理（冪等）

---

### 2. `update_stocks_price.py` の変更点
**ファイル：** `cloud-job/update_stocks_price.py`

**変更箇所3か所（差分最小）：**

1. `from BackcastPro.api.db_stocks_daily_mother import db_stocks_daily_mother` を追加
2. `mother_db = db_stocks_daily_mother()` をシングルトン初期化ブロックに追加
3. `sp.db.save_stock_prices(code, final_df)` → `mother_db.save_stock_prices(code, final_df)` に変更
4. ループ完了後に `split_to_individual(sp.db, from_date=from_date.strftime(...))` を追加

`sp.db`（既存 `db_stocks_daily` インスタンス）をそのまま `individual_db` として渡す。
`from_date` は line 101 で定義済みのため**再計算不要**。

---

### 3. GraphQL エンドポイント
**ファイル：** `cloud-run/main.py`

| エンドポイント | クエリ | 説明 |
|---|---|---|
| `POST /graphql` | `gainRanking(date, limit)` | 値上がり率ランキング |
| `POST /graphql` | `declineRanking(date, limit)` | 値下がり率ランキング |
| `POST /graphql` | `volumeRanking(date, limit)` | 出来高ランキング |

**ライブラリ：** `strawberry-graphql[flask]`（型ヒントベース、モダン）

**SQL インジェクション対策：**
`ORDER BY` 句の `{order}` は `_ORDER_MAP = {"desc": "DESC", "asc": "ASC"}` でホワイトリスト化。
その他の可変値はすべて DuckDB のパラメータバインド（`?`）で処理。

**値上がり率のSQL概要：**
```sql
WITH target AS (SELECT Code, Close, Volume FROM stocks_daily WHERE Date = ?),
prev AS (
    SELECT s.Code, s.Close AS PrevClose
    FROM stocks_daily s
    INNER JOIN (SELECT Code, MAX(Date) AS PrevDate FROM stocks_daily WHERE Date < ? GROUP BY Code) p
    ON s.Code = p.Code AND s.Date = p.PrevDate
)
SELECT ..., (t.Close - pr.PrevClose) / pr.PrevClose * 100 AS GainRate, ROW_NUMBER() OVER (ORDER BY GainRate DESC) AS Rank
FROM target t JOIN prev pr ON t.Code = pr.Code WHERE pr.PrevClose > 0
ORDER BY GainRate DESC LIMIT ?
```

**注：** DuckDB は同一 SELECT の `AS GainRate` エイリアスを `WINDOW` 関数内で参照できる。

**ALLOWED_PATHS の変更：**
```
# 変更前: stocks_daily/\d+\.duckdb
# 変更後: stocks_daily/(?:\d+|mother)\.duckdb
```
`(?:\d+|mother)` で mother.duckdb へのファイル配信も許可（ `/graphql` とは別の用途）。

---

## 設計判断の記録

### なぜ GraphQL か
- ランキングの種類・件数などクライアント側が柔軟に選択できる
- 将来的に銘柄情報（会社名・業種など）との JOIN も同一クエリで拡張しやすい
- REST と比べて仕様変更時のバージョン管理が容易

### なぜ事前集計しないか
- 母DBに全期間の全銘柄データが入っているため、1クエリで完結する
- 日次バッチとは別プロセスで集計を管理するコストが高い
- DuckDB の列指向クエリは ON-THE-FLY 集計でも十分高速

### なぜ mother.duckdb を個別DBの派生とするか
- **単一の真実の源** を持つことで二重管理のズレを防ぐ
- mother.duckdb が壊れても個別DBから再構築できる
- 個別DBへの書き込みは `save_stock_prices()` の冪等性に任せる

### DuckDB の WAL による同時アクセス
Cloud Job（書き込み）と Cloud Run（read_only）が同時にアクセスする可能性があるが、
DuckDB の WAL（Write-Ahead Logging）モードで read_only 接続は常に許容される。
日次バッチは深夜短時間で完了するため、実運用上の競合リスクは低い。

---

## 初回デプロイ手順（新環境 / mother.duckdb 未存在時）

既存の個別DBがない新環境では、過去データを含む完全移行が必要：

```bash
# Step 1: 全銘柄 × 過去データを mother.duckdb へ投入（例: 過去3年分）
python update_stocks_price.py --days 1000

# Step 2: mother.duckdb → 個別DB へ全量分割（from_date=None で全期間）
# --days N の split は直近N日分のみのため、初回は手動で全期間 split が必要
python - <<'EOF'
import os, sys
sys.path.insert(0, "/app/src")
os.environ["STOCKDATA_CACHE_DIR"] = os.environ.get("STOCKDATA_CACHE_DIR", "/cache")
from BackcastPro.api.db_stocks_daily_mother import db_stocks_daily_mother
from BackcastPro.api.db_stocks_daily import db_stocks_daily
result = db_stocks_daily_mother().split_to_individual(db_stocks_daily(), from_date=None)
print(result)
EOF
```

日次運用：`update_stocks_price.py --days 7` のみ。差分 fetch → mother.duckdb upsert → 個別DB split が自動実行される。

---

## Tips・注意事項

### `db_stocks_daily_mother` を使う際の注意
- `ensure_db_ready(code)` が内部で呼ばれるが、`code` 引数は**無視されて mother.duckdb のパスが使われる**。
  これは意図した動作（`_db_subdir=None` により code がパスに使われない）。
- `load_stock_prices_from_cache(code, ...)` は mother.duckdb に対して動作するが、
  通常は個別DBから読む `sp.db` を経由することが多いため、母DBからの直接 load は
  ランキング用途以外では使わないこと。

### split_to_individual の性能
- 4,000銘柄で接続1回 → `save_stock_prices()` は銘柄ごとに個別DBを開閉する（内部で `get_db(code)`）
- 実質的には 1（母DB接続）+ 4,000（個別DB接続）の合計アクセスになる
- `save_stock_prices()` 内の重複チェックは `Code, Date` の Set 比較で O(n)

### GraphQL の `StockRankingItem` 型
- `volume_ranking` では `prev_close=None, gain_rate=None` が返る（gain/decline では常に値が入る）
- クライアント側でフィールドの Nullable を考慮すること

### 銘柄コードの正規化
- `_normalize_code()` (db_manager.py:341) は 5桁コード末尾の `0` を除去して4桁にする
- mother.duckdb に保存される `Code` の形式は API ソースによって異なる場合がある
  （例：`7203` vs `7203.JP` vs `72030`）。一貫性を保つため、保存前に正規化を確認すること

### 将来的な拡張
- **業種別ランキング** を追加する場合は `listed_info.duckdb` と mother.duckdb を ATTACH して JOIN
- **キャッシュレイヤー** を追加したい場合は `/graphql` の前段に nginx や CloudFlare Workers で
  日次結果をキャッシュする方法が最もシンプル

---

## 検証チェックリスト

- [ ] `python update_stocks_price.py --codes 7203,8306 --days 7`
- [✅] `python update_stocks_price.py --codes 7203,8306 --days 7`
  → `S:\jp\stocks_daily\mother.duckdb` に2銘柄が入り `7203.duckdb` が生成される
- [✅] 同コマンドを2回実行 → 重複データなし（冪等性）
- [✅] `{ gainRanking(date: "2025-01-10", limit: 5) { code gainRate rank } }`
  → 結果が返る
- [✅] `GET /jp/stocks_daily/mother.duckdb` → 200 OK
- [✅] `get_stock_daily("7203")` or `get_stock_daily("7203")` が引き続き動作する（個別ファイルから読み込み）

---

## 検証結果 (2026-02-28 実施)

上記のプランに基づき、実装およびすべての検証項目をクリアしたことを確認しました。

1. **`update_stocks_price.py` 実行とファイル生成**
   - 正常に完了し、`S:\jp\stocks_daily\mother.duckdb` および `7203.duckdb`、`8306.duckdb` が分割・生成されることを確認しました。
2. **冪等性の確認**
   - 2回実行後、`mother.duckdb` 内の `duplicate` を確認（`GROUP BY Code, Date HAVING c > 1`）した結果、重複行が 0 件であることを確認しました。
3. **GraphQL クエリ確認**
   - 開発サーバー (`cloud-run/main.py`) を起動し、`gainRanking` および `volumeRanking` より想定通りのランキング項目が取得できることを確認しました。
   - *（注：検証時に `strawberry-graphql` の新バージョンに伴うインポートエラーが発生したため、`main.py` 内のインポートを `from strawberry.flask.views import GraphQLView` へ修正しました）*
4. **ホワイトリストアクセス確認**
   - `GET /jp/stocks_daily/mother.duckdb` に対して 200 OK で正常にファイルバイナリデータが取得できることを確認しました。
5. **後方互換性の確認**
   - `get_stock_daily("7203")` を実行し、既存通り個別ファイル (`7203.duckdb`) から正常にデータ(6088行)が読み込まれ、DatetimeIndex も維持されていることを確認しました。
