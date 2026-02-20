# J-Quants データダウンロード引継ぎ資料

## 目的
J-Quants Webサイトから2026年1月（月次分）および2月（日次分）の以下のデータを `S:\j-quants` にダウンロードする。
- 株価四本値 (Daily Bars)
- 株価分足 (Minute Bars)
- 株価ティック (Trades)

## 作業状況
- ブラウザエージェントは既に J-Quants ダッシュボードにログイン済みです。
- ファイルキーのパターンは特定済みですが、取得用URL（署名付きURL）は **300秒（5分）で有効期限が切れる** ため、一括でURLを取得してからダウンロードするのではなく、取得後すぐにダウンロードする必要があります。

## 対象ファイルリスト (2026年)

### 1. 2026年1月 (月次一括)
- `equities_bars_daily_202601.csv.gz`
- `equities_bars_minute_202601.csv.gz`
- `equities_trades_202601.csv.gz`

### 2. 2026年2月 (日次)
日付: 02, 03, 04, 05, 06, 09, 10, 12, 13, 16, 17, 18
(例: `equities_bars_daily_20260218.csv.gz`)

## URL取得方法 (ブラウザエージェントへの依頼)
ダッシュボードページ (`https://jpx-jquants.com/ja/dashboard/downloads/price-data/stocks`) で以下のJavaScriptを実行してURLを取得してください。

```javascript
(async () => {
  const key = "対象のファイルキー"; // 例: equities/bars/daily/live/equities_bars_daily_20260218.csv.gz
  const res = await fetch('/api/trpc/bulk.bulkGet?batch=1', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ "0": { "json": { "key": key } } })
  });
  const data = await res.json();
  return data[0]?.result?.data?.json; // 署名付きURLが返る
})()
```

### キーの指定ルール
- **2026/01**: `equities/[カテゴリ]/historical/2026/equities_[名前]_202601.csv.gz`
- **2026/02**: `equities/[カテゴリ]/live/equities_[名前]_202602[日付].csv.gz`
  - カテゴリ/名前の対応:
    - 株価四本値: `bars/daily` / `bars_daily`
    - 株価分足: `bars/minute` / `bars_minute`
    - 株価ティック: `trades` / `trades`

## ダウンロード実行方法 (PowerShell)
取得したURL（`$URL`）を使って、Windowsの `curl.exe` で保存します。

```powershell
curl.exe -L "$URL" -o "S:\j-quants\filename.csv.gz"
```

## 注意事項
- **有効期限**: URLは5分で切れます。1ファイルずつ「URL取得 -> 即座にダウンロード」のサイクルを繰り返してください。
- **保存先**: `S:\j-quants` 固定です。
- **2月のキー**: 現在（2026/02）は `live` パスにあるものが多いですが、失敗した場合は `historical/2026/02/` パスを試してください。
- **残存ファイル**: `S:\j-quants` に容量0のファイルや無効なXMLエラーが含まれるファイルがある場合は上書きしてください。
