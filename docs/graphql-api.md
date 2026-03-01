# GraphQL ランキング API

`cloud-run/main.py` が提供する GraphQL エンドポイント（`/graphql`）の使い方ガイド。

## エンドポイント

| 環境 | URL |
|------|-----|
| ローカル開発 | `http://localhost:8080/graphql` |
| Cloud Run | デプロイ先 URL + `/graphql` |

---

## メインクエリ：`stockRankingRange`

**「何のランキングか」はクライアント側が `sortBy` + `order` で決定する。**
バックエンドは汎用的なデータを返すだけで、ランキング種別をクエリ名に埋め込まない。

### パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `fromDate` | `String` | 必須 | 開始日 `YYYY-MM-DD` |
| `toDate` | `String` | 必須 | 終了日 `YYYY-MM-DD` |
| `sortBy` | `String` | `"gain_rate"` | ランキング基準（後述） |
| `order` | `String` | `"desc"` | `"desc"` または `"asc"` |
| `limit` | `Int` | `20` | 各日のTop-N件数 |

### レスポンス型 `DailyRankingItem`

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `date` | `String` | 日付 `YYYY-MM-DD` |
| `code` | `String` | 銘柄コード |
| `close` | `Float` | 終値 |
| `prevClose` | `Float?` | 前営業日終値（初日など取得できない場合 null） |
| `gainRate` | `Float?` | 騰落率 `(close - prevClose) / prevClose × 100` |
| `volume` | `Float?` | 出来高 |
| `rank` | `Int` | 順位（各日 1〜limit） |

---

## sortBy の種類

現在サポートされている `sortBy` 値：

| sortBy | ランキング種別 | 計算元 |
|--------|-------------|--------|
| `"gain_rate"` | 値上がり率 / 値下がり率 | `(Close - PrevClose) / PrevClose × 100` |
| `"volume"` | 出来高 | `Volume` |

> 追加予定: `"turnover_value"` (売買代金 = Close × Volume)、`"price_range_rate"` (値幅率) など。

---

## クエリ例

### 値上がり率ランキング（Top 20、1ヶ月分）

```graphql
query GainRanking {
  stockRankingRange(
    fromDate: "2025-01-01"
    toDate:   "2025-01-31"
    sortBy:   "gain_rate"
    order:    "desc"
    limit:    20
  ) {
    date
    code
    close
    gainRate
    rank
  }
}
```

### 値下がり率ランキング（同じクエリ、order: "asc" のみ変更）

```graphql
query DeclineRanking {
  stockRankingRange(
    fromDate: "2025-01-01"
    toDate:   "2025-01-31"
    sortBy:   "gain_rate"
    order:    "asc"
    limit:    20
  ) {
    date
    code
    close
    gainRate
    rank
  }
}
```

### 出来高ランキング

```graphql
query VolumeRanking {
  stockRankingRange(
    fromDate: "2025-01-01"
    toDate:   "2025-01-31"
    sortBy:   "volume"
    order:    "desc"
    limit:    20
  ) {
    date
    code
    close
    volume
    rank
  }
}
```

---

## curl での呼び出し例

```bash
curl -X POST http://localhost:8080/graphql \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{ stockRankingRange(fromDate: \"2025-01-06\", toDate: \"2025-01-10\", sortBy: \"gain_rate\", order: \"desc\", limit: 5) { date code gainRate rank } }"
  }'
```

レスポンス例（抜粋）：

```json
{
  "data": {
    "stockRankingRange": [
      {"date": "2025-01-06", "code": "3137", "gainRate": 36.3636, "rank": 1},
      {"date": "2025-01-06", "code": "3624", "gainRate": 29.8013, "rank": 2},
      ...
      {"date": "2025-01-07", "code": "2962", "gainRate": 31.6206, "rank": 1},
      ...
    ]
  }
}
```

---

## レスポンスサイズの目安

| limit | 営業日数（10年） | JSON目安 | gzip後 |
|-------|----------------|---------|--------|
| 20 | ~2,450日 → ~49,000行 | ~5MB | ~0.8MB |
| 50 | ~2,450日 → ~122,500行 | ~12MB | ~2MB |

1リクエストで複数年分をまとめて取得できる設計のため、クライアント側でキャッシュすれば再クエリ不要。

---

## セキュリティ

`sortBy` / `order` はホワイトリスト (`_SORT_COL_MAP`, `_ORDER_MAP`) で検証する。
無効な値を渡すと `KeyError` → GraphQL エラーとして返却され、SQL には渡らない。

```python
# cloud-run/main.py
_SORT_COL_MAP = {
    "gain_rate": "GainRate",
    "volume":    '"Volume"',
}
_ORDER_MAP = {"desc": "DESC", "asc": "ASC"}
```

---

## ローカル起動方法

```bash
cd cloud-run
# .env に STOCKDATA_CACHE_DIR=S:/ を設定済みであること
python main.py
# → http://localhost:8080/graphql
```

依存ライブラリは `cloud-run/requirements.txt`（`strawberry-graphql[flask]`, `duckdb` など）。

---

## 新しいランキング種別の追加方法

`_SORT_COL_MAP` に追加するだけで対応できる：

```python
# 例: 高値ランキングを追加
_SORT_COL_MAP = {
    "gain_rate":     "GainRate",
    "volume":        '"Volume"',
    "high":          '"High"',       # ← 追加
    "turnover_value": "TurnoverVal", # ← WITH句への計算列追加も必要
}
```

`High` / `Low` / `Open` などは `stocks_daily` に実カラムとして存在するため即追加可能。
`TurnoverValue`（= `Close × Volume`）のような計算列は `ranked` CTE の `SELECT` にも追加が必要。

---

## 関連ドキュメント

- [mother.duckdb 統合DBの設計経緯](design-decisions.md#motherduckdb-統合dbの導入と-graphql-ランキングapi)
- [Docker job によるデータ更新](cloud-run-updater.md)
