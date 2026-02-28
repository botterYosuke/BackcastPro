# 株式ランキングデータ取得・保存タスク

## 進捗サマリー

| 項目 | 状況 |
|---|---|
| `src/BackcastPro/api/db_stocks_ranking.py` | ✅ 実装・テスト完了 |
| `cloud-job/update_stocks_ranking.py` | ✅ 実装・テスト完了（バグ修正済み） |
| `--backfill` オプション追加 | 🔲 **未実装（次の作業者のタスク）** |

---

## 次の作業者のタスク：`--backfill` オプション実装

### 概要
`stocks_daily` に存在して `stocks_ranking.duckdb` に未保存の日付を自動検出し、
一括で欠損日を補完するオプション `--backfill` を `update_stocks_ranking.py` に追加する。

### 実行イメージ
```bash
# 初回起動時：全欠損日を自動補完
python cloud-job/update_stocks_ranking.py --backfill

# 通常運用（毎日夜間）：最新1日分のみ処理
python cloud-job/update_stocks_ranking.py
```

### 実装仕様

**① argparse に `--backfill` フラグを追加**（`parse_arguments()` 内）
```python
parser.add_argument(
    "--backfill",
    action="store_true",
    help="stocks_daily にあって stocks_ranking にない日付を全て補完する",
)
```

**② `find_missing_dates()` 関数を追加**
```python
def find_missing_dates(codes_sample: list[str], db_ranking: db_stocks_ranking) -> list[str]:
    """stocks_daily 全日付 − stocks_ranking 保存済み日付 = 未処理日付リスト（昇順）"""
    # 代表銘柄 5件の DISTINCT Date を UNION して全営業日を取得
    db_daily = db_stocks_daily()
    all_dates: set[str] = set()
    for code in codes_sample[:5]:
        try:
            with db_daily.get_db(code) as db:
                if not db_daily._table_exists(db, "stocks_daily"):
                    continue
                rows = db.execute(
                    'SELECT DISTINCT "Date" FROM stocks_daily WHERE "Code" = ?', [code]
                ).fetchall()
                all_dates.update(pd.Timestamp(r[0]).strftime("%Y-%m-%d") for r in rows)
        except Exception:
            continue

    # stocks_ranking の保存済み日付を取得
    done_dates: set[str] = set()
    try:
        with db_ranking.get_db() as db:
            if db_ranking._table_exists(db, "price_rankings"):
                rows = db.execute(
                    'SELECT DISTINCT "Date" FROM price_rankings'
                ).fetchall()
                done_dates = {str(r[0])[:10] for r in rows}
    except Exception:
        pass

    missing = sorted(all_dates - done_dates)
    logger.info(f"バックフィル対象: {len(missing)} 日 (全{len(all_dates)}日中 {len(done_dates)}日保存済み)")
    return missing
```

**③ `main()` のロジック変更**（対象日決定ブロックを置き換え）
```python
# 対象日リストの決定
if args.backfill:
    dates = find_missing_dates(master["Code"].tolist(), db_ranking)
    if not dates:
        logger.info("バックフィル: 全日付が処理済みです")
        return 0
elif args.date:
    base_dt = datetime.strptime(args.date, "%Y-%m-%d")
    dates = [(base_dt - timedelta(days=d)).strftime("%Y-%m-%d") for d in range(args.days)]
else:
    base_date = detect_latest_date(master["Code"].tolist())
    if not base_date:
        logger.error("DuckDB 内の最新日付が検出できません")
        return 1
    logger.info(f"対象日を自動検出: {base_date}")
    base_dt = datetime.strptime(base_date, "%Y-%m-%d")
    dates = [(base_dt - timedelta(days=d)).strftime("%Y-%m-%d") for d in range(args.days)]
```

### テスト方法
```bash
# 動作確認（少数銘柄）
STOCKDATA_CACHE_DIR='C:\Users\sasai\SynologyDrive\StockData' \
PYTHONPATH='src' \
python cloud-job/update_stocks_ranking.py --backfill --codes 130A,9425
```
期待する動作:
- 初回: `stocks_daily` の全日付が処理される
- 2回目: 「全日付が処理済みです」で即終了

---

## プロジェクト構造と重要ファイル

```
BackcastPro/
├── cloud-job/
│   ├── update_stocks_price.py      # 既存：夜間株価更新（参照パターン）
│   └── update_stocks_ranking.py    # ✅ 新規：ランキング計算・保存
├── src/BackcastPro/api/
│   ├── db_manager.py               # 基底クラス（get_db, _table_exists, etc.）
│   ├── db_stocks_daily.py          # 株価DB（load_stock_prices_from_cache 利用）
│   ├── db_stocks_info.py           # 銘柄マスタDB（load_listed_info_from_cache）
│   └── db_stocks_ranking.py        # ✅ 新規：ランキングDB
└── tests/
    └── import_equities_trades.py   # stocks_trades スキーマ確認用
```

---

## DB 設計

**ファイルパス:** `{STOCKDATA_CACHE_DIR}/jp/stocks_ranking.duckdb`

### `price_rankings` テーブル（銘柄別 7種）
| カラム | 型 | 説明 |
|---|---|---|
| Date | DATE | 対象日 |
| RankType | VARCHAR(50) | `gain_rate` / `decline_rate` / `volume_high` / `turnover_value` / `tick_count` / `volume_surge` / `turnover_surge` |
| Rank | INTEGER | 順位 (1〜100) |
| Code | VARCHAR(10) | 銘柄コード（4桁） |
| CompanyName | VARCHAR | 会社名 |
| Sector17Code | VARCHAR(10) | 17業種コード |
| Sector17CodeName | VARCHAR | 17業種名 |
| Value | DOUBLE | 指標値 |
| PRIMARY KEY | (Date, RankType, Rank) | |

### `sector_rankings` テーブル（業種別 2種）
| カラム | 型 | 説明 |
|---|---|---|
| Date | DATE | 対象日 |
| RankType | VARCHAR(50) | `sector_gain_rate` / `sector_decline_rate` |
| Rank | INTEGER | |
| Sector17Code | VARCHAR(10) | |
| Sector17CodeName | VARCHAR(100) | |
| Value | DOUBLE | セクター平均変化率 (%) |
| StockCount | INTEGER | セクター内銘柄数 |
| PRIMARY KEY | (Date, RankType, Rank) | |

---

## 設計思想と知見（Tips）

### db_manager のパスルール
`db_manager._get_db_path()` の挙動:
- `_db_subdir` あり + code あり → `{cache}/jp/{subdir}/{code}.duckdb`（per-stock）
- `_db_subdir` なし + `_db_filename` あり → `{cache}/jp/{filename}`（単一ファイル）

ランキングは単一ファイルで管理するため `_db_filename = "stocks_ranking.duckdb"` のみ設定。
`db_stocks_info.py`（`listed_info.duckdb`）と同じパターン。

### `db_manager` のシングルトン問題に注意
`jquants`, `e_api` はシングルトン。`db_stocks_ranking` / `db_stocks_daily` はシングルトンではないが、
同一スクリプト内でインスタンスを複数作ると `STOCKDATA_CACHE_DIR` の上書きが複雑になるので
各クラスは1インスタンスに保つこと。

### 冪等性の保証（save_rankings）
保存は `DELETE WHERE Date=? AND RankType=?` → `INSERT` の2ステップ。
同じ日付を2回実行しても重複しない。トランザクションで原子性を保証済み。

### TICK回数データの実態
`stocks_trades` ディレクトリのファイルに `stocks_board` テーブルが入っているケースがある。
（`import_equities_trades.py` では `stocks_trades` テーブルを想定しているが、
実際のファイルは `stocks_board` テーブルを含む場合がある）

`collect_tick_counts()` はテーブル名を動的に確認して対応:
- `stocks_trades` テーブル → `COUNT("TransactionId")`
- `stocks_board` テーブル → `COUNT(*)`（行数 ≒ TICK回数）

### `detect_latest_date()` の実装注意
`load_stock_prices_from_cache()` に日付範囲を渡すと period coverage check が走り、
データが古い場合（DuckDB の最新が数ヶ月前など）は空を返してしまう。
→ `get_db()` で直接 `SELECT MAX("Date")` を叩くことで回避済み。

### Python 3.9 対応
`list[str] | None` 等の組み込みジェネリクスは Python 3.10+。
ファイル先頭に `from __future__ import annotations` を追加して対応済み。

### TurnoverValue の欠損
一部データソースでは `TurnoverValue` カラムが存在しない場合がある。
`collect_price_data()` で動的確認し、なければ NaN。
`turnover_value` / `turnover_surge` ランキングは `dropna()` で NaN 除外。

---

## テスト済み環境

```
STOCKDATA_CACHE_DIR = C:\Users\sasai\SynologyDrive\StockData
PYTHONPATH = src
実行: python cloud-job/update_stocks_ranking.py --codes 130A,9425
結果: 2025-10-31 の price_rankings 12件、sector_rankings 4件を正常保存
```

---

## 実行コマンド早見表

```bash
cd C:\Users\sasai\Documents\BackcastPro
$env:STOCKDATA_CACHE_DIR = "C:\Users\sasai\SynologyDrive\StockData"
$env:PYTHONPATH = "src"

# 通常運用（最新1日）
python cloud-job/update_stocks_ranking.py

# バックフィル（実装後）
python cloud-job/update_stocks_ranking.py --backfill

# テスト（2銘柄）
python cloud-job/update_stocks_ranking.py --codes 130A,9425

# 特定日・複数日
python cloud-job/update_stocks_ranking.py --date 2025-10-31 --days 5
```
