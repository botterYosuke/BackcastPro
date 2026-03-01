# GraphQL ランキング API

`cloud-run/main.py` が提供する GraphQL エンドポイント（`/graphql`）の使い方ガイド。

## エンドポイント

| 環境 | URL |
|------|-----|
| ローカル開発 | `http://localhost:8080/graphql` |
| Cloud Run | デプロイ先 URL + `/graphql` |

---

## メインクエリ：`stockRankingRange`

**「何のランキングか」はクライアント側が `sortBy` に計算式を直接渡して決定する。**
バックエンドは式を検証・変換して DuckDB に渡し、汎用的なデータを返す。

### パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `fromDate` | `String` | 必須 | 開始日 `YYYY-MM-DD` |
| `toDate` | `String` | 必須 | 終了日 `YYYY-MM-DD` |
| `sortBy` | `String` | `"(Close - Close[-1]) / Close[-1] * 100"` | ソート計算式（後述） |
| `order` | `String` | `"desc"` | `"desc"` または `"asc"` |
| `limit` | `Int` | `20` | 各日のTop-N件数 |

### レスポンス型 `DailyRankingItem`

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `date` | `String` | 日付 `YYYY-MM-DD` |
| `code` | `String` | 銘柄コード |
| `close` | `Float` | 終値 |
| `prevClose` | `Float?` | 常に `null`（廃止済み、後述） |
| `sortValue` | `Float?` | `sortBy` 式の計算結果（null の行は順位末尾） |
| `volume` | `Float?` | 出来高 |
| `rank` | `Int` | 順位（各日 1〜limit） |

---

## sortBy の書き方

`sortBy` には **使用可能な列名と四則演算子・括弧・数値** で構成された計算式を文字列で渡す。

### 使用可能な列名

| 列名 | 内容 |
|------|------|
| `Close` | 終値 |
| `Open` | 始値 |
| `High` | 高値 |
| `Low` | 安値 |
| `Volume` | 出来高 |

### ラグ指定（任意の前営業日値）

`ColName[-N]` の形式で **N 営業日前** の値を参照できる。

| 記法 | 内容 |
|------|------|
| `Close[-1]` | 前営業日の終値 |
| `Close[-2]` | 2営業日前の終値 |
| `Open[-3]` | 3営業日前の始値 |
| `Volume[-1]` | 前営業日の出来高 |

- N は 1 以上の整数
- 値が 0 の場合は自動的に `NULL` 扱い（ゼロ除算防止）
- バックエンドが必要な営業日数分だけ自動でデータを遡って取得する

### 使用可能な演算子・記号

`+` `-` `*` `/` `(` `)` および数値リテラル

### 計算式の例

| sortBy 文字列 | ランキング種別 |
|--------------|--------------|
| `"(Close - Close[-1]) / Close[-1] * 100"` | 騰落率（%） ← デフォルト |
| `"(Close - Close[-2]) / Close[-2] * 100"` | 2日間騰落率（%） |
| `"Volume"` | 出来高 |
| `"(High - Low) / Close * 100"` | 値幅率（%） |
| `"Close * Volume"` | 売買代金 |
| `"High - Low"` | 値幅（絶対値） |
| `"Close / High[-3] * 100"` | 3日前高値に対する比率（%） |
| `"Volume / Volume[-1]"` | 出来高前日比 |

> **注意**: 列名・演算子以外の文字列（関数名・セミコロン等）は検証エラーになります。

---

## クエリ例

### 騰落率ランキング（Top 20、1ヶ月分）

```graphql
query GainRanking {
  stockRankingRange(
    fromDate: "2025-01-01"
    toDate:   "2025-01-31"
    sortBy:   "(Close - Close[-1]) / Close[-1] * 100"
    order:    "desc"
    limit:    20
  ) {
    date
    code
    close
    sortValue
    rank
  }
}
```

### 値下がり率ランキング（order: "asc" に変更）

```graphql
query DeclineRanking {
  stockRankingRange(
    fromDate: "2025-01-01"
    toDate:   "2025-01-31"
    sortBy:   "(Close - Close[-1]) / Close[-1] * 100"
    order:    "asc"
    limit:    20
  ) {
    date
    code
    close
    sortValue
    rank
  }
}
```

### 2日間騰落率ランキング

```graphql
query TwoDayGainRanking {
  stockRankingRange(
    fromDate: "2025-01-01"
    toDate:   "2025-01-31"
    sortBy:   "(Close - Close[-2]) / Close[-2] * 100"
    order:    "desc"
    limit:    10
  ) {
    date
    code
    close
    sortValue
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
    sortBy:   "Volume"
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

### 値幅率ランキング（ボラティリティスクリーニング）

```graphql
query VolatilityRanking {
  stockRankingRange(
    fromDate: "2025-01-01"
    toDate:   "2025-01-31"
    sortBy:   "(High - Low) / Close * 100"
    order:    "desc"
    limit:    10
  ) {
    date
    code
    close
    sortValue
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
    "query": "{ stockRankingRange(fromDate: \"2025-01-06\", toDate: \"2025-01-10\", sortBy: \"(Close - Close[-1]) / Close[-1] * 100\", order: \"desc\", limit: 5) { date code sortValue rank } }"
  }'
```

レスポンス例（抜粋）：

```json
{
  "data": {
    "stockRankingRange": [
      {"date": "2025-01-06", "code": "3137", "sortValue": 36.3636, "rank": 1},
      {"date": "2025-01-06", "code": "3624", "sortValue": 29.8013, "rank": 2},
      ...
      {"date": "2025-01-07", "code": "2962", "sortValue": 31.6206, "rank": 1},
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

`sortBy` はトークンベースのホワイトリスト検証 (`_parse_formula`) を通過した式のみ DuckDB に渡る。
許可トークン以外（関数名・セミコロン等）が含まれると `ValueError` → GraphQL エラーとして返却される。

```python
# cloud-run/main.py（抜粋）
_COL_MAP = {
    "Close":  '"Close"',
    "Open":   '"Open"',
    "High":   '"High"',
    "Low":    '"Low"',
    "Volume": '"Volume"',
}
# ColName[-N] は LAG("ColName", N) に変換、値 0 は NULLIF で NULL 扱い
_ORDER_MAP = {"desc": "DESC", "asc": "ASC"}
```

`order` は `_ORDER_MAP` ホワイトリストで検証する（無効値は `KeyError`）。

---

## `prevClose` フィールドについて（廃止）

旧バージョンでは `PrevClose` という固定の列名をサポートし、レスポンスの `prevClose` フィールドに
前営業日終値を返していた。現バージョンでは `Close[-1]` 構文に統一されたため、
`prevClose` は常に `null` を返す（フィールド自体は互換性のために残存）。

移行方法：

```
# 旧
sortBy: "(Close - PrevClose) / PrevClose * 100"

# 新
sortBy: "(Close - Close[-1]) / Close[-1] * 100"
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

`sortBy` に計算式を直接渡すだけで新種別を追加できる。
バックエンドの変更は **不要**。

新しい列を使いたい場合（例: `Turnover` など `stocks_daily` にない計算列）は、
`cloud-run/main.py` の `extended` CTE と `_COL_MAP` / `_TOKEN_RE` への追加が必要。

---

## 関連ドキュメント

- [mother.duckdb 統合DBの設計経緯](design-decisions.md#motherduckdb-統合dbの導入と-graphql-ランキングapi)
- [Docker job によるデータ更新](cloud-run-updater.md)
