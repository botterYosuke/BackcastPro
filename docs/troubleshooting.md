# <img src="img/logo.drawio.svg" alt="BackcastPro Logo" width="40" height="24"> トラブルシューティングガイド

BackcastProを使用する際によく発生する問題とその解決方法をまとめています。

## 目次

- [インストール関連の問題](#インストール関連の問題)
- [データ関連の問題](#データ関連の問題)
- [戦略実装の問題](#戦略実装の問題)
- [バックテスト実行の問題](#バックテスト実行の問題)
- [パフォーマンスの問題](#パフォーマンスの問題)
- [エラーメッセージ一覧](#エラーメッセージ一覧)

## インストール関連の問題

### 問題: `ModuleNotFoundError: No module named 'BackcastPro'`

**原因:** BackcastProが正しくインストールされていない

**解決方法:**
```powershell
# PyPIから再インストール
python -m pip install BackcastPro

# または開発用インストール
git clone <repository-url>
cd BackcastPro
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

### 問題: `ImportError: cannot import name 'XXX'`

**原因:** 古いバージョンがインストールされている、またはインストールが不完全

**解決方法:**
```powershell
# 既存のインストールをアンインストール
python -m pip uninstall BackcastPro -y

# 最新版を再インストール
python -m pip install --upgrade BackcastPro

# インストールを確認
python -c "from BackcastPro import Backtest, get_stock_daily, get_stock_board, get_stock_info; print('OK')"
```

### 問題: 依存関係の競合

**原因:** 他のライブラリとの依存関係の競合

**解決方法:**
```powershell
# 仮想環境を作成（Windows）
python -m venv backcastpro_env
.\backcastpro_env\Scripts\Activate.ps1

# クリーンな環境でインストール
python -m pip install BackcastPro
```

## データ関連の問題

### 問題: `TypeError: data[XXX] must be a pandas.DataFrame with columns`

**原因:** データが辞書形式でない、またはDataFrameでない

**解決方法:**
```python
# 正しい形式: 辞書で銘柄コードをキーとしてDataFrameを渡す
bt = Backtest(
    data={
        '7203.T': toyota_data,
        '6758.T': sony_data
    },
    cash=10000
)

# 単一銘柄の場合も辞書形式で渡す
bt = Backtest(data={'7203.T': toyota_data}, cash=10000)
```

### 問題: `ValueError: data must be a pandas.DataFrame with columns`

**原因:** DataFrameに必要な列がない

**解決方法:**
```python
import pandas as pd

# 必要な列を確認
required_columns = ['Open', 'High', 'Low', 'Close']
if not all(col in data.columns for col in required_columns):
    print("不足している列:", [col for col in required_columns if col not in data.columns])
    # 不足している列を追加
    for col in required_columns:
        if col not in data.columns:
            data[col] = data['Close']  # 終値で補完
```

### 問題: `ValueError: Some OHLC values are missing (NaN)`

**原因:** OHLCデータに欠損値がある

**解決方法:**
```python
# 欠損値を確認
print(data.isnull().sum())

# 欠損値を削除
data = data.dropna()

# または補間
data = data.interpolate()

# または前の値で埋める
data = data.fillna(method='ffill')
```

### 問題: `requests.RequestException: Failed to fetch data from API`

**原因:** API接続の問題

**解決方法:**
```python
# 1. インターネット接続を確認
import requests
try:
    response = requests.get('https://httpbin.org/get', timeout=5)
    print("インターネット接続: OK")
except:
    print("インターネット接続: NG")

# 2. 環境変数を確認
import os
print("API URL:", os.getenv('BACKCASTPRO_API_URL'))
print("NAS Proxy URL:", os.getenv('BACKCASTPRO_GDRIVE_API_URL'))

# 3. 手動でデータを設定
custom_data = pd.DataFrame({
    'Open': [100, 101, 102],
    'High': [105, 106, 107],
    'Low': [99, 100, 101],
    'Close': [104, 105, 106],
    'Volume': [1000, 1100, 1200]
}, index=pd.date_range('2023-01-01', periods=3))
```

### 問題: Cloud Run API経由のデータダウンロード失敗

**原因:** Cloud Run APIのURLが設定されていない、Proxyが停止している、またはNASに接続できない。

**解決方法:**
1. `.env` ファイルで `BACKCASTPRO_GDRIVE_API_URL`（NAS FTPS Proxy のURL、歴史的経緯で GDRIVE の名前が残っている）が正しく設定されているか確認してください。
2. APIが起動しているかブラウザでアクセスして確認してください（`https://.../`で`OK`が返ること）。
3. NASが稼働中でFTPSサーバーが有効か確認してください。

### 問題: データが空または取得できない

**原因:** 銘柄コードが間違っている、または期間が無効

**解決方法:**
```python
import yfinance as yf

# 1. 期間を確認
from datetime import datetime, timedelta
end_date = datetime.now()
start_date = end_date - timedelta(days=365)
print(f"期間: {start_date} から {end_date}")

# 2. 異なる銘柄で試す
data = yf.download('7203.T', period='1y')  # トヨタ
if data is None or len(data) == 0:
    print("データが取得できませんでした")
```

## 戦略実装の問題

### 問題: 戦略関数が呼ばれない

**原因:** `set_strategy()` を呼んでいない、または戦略関数のシグネチャが間違っている

**解決方法:**
```python
from BackcastPro import Backtest

# 正しい実装: 関数ベースの戦略
def my_strategy(bt):
    """戦略関数は (bt) を引数に取る"""
    for code, df in bt.data.items():
        if len(df) < 2:
            continue

        pos = bt.position_of(code)
        if pos == 0:
            bt.buy(code=code, tag="entry")

# 方法1: set_strategy + run
bt = Backtest(data={'TEST': df}, cash=10000)
bt.set_strategy(my_strategy)
results = bt.run()

# 方法2: 手動ループ
bt = Backtest(data={'TEST': df}, cash=10000)
while not bt.is_finished:
    my_strategy(bt)
    bt.step()
results = bt.finalize()
```

### 問題: `AttributeError: 'Backtest' object has no attribute 'XXX'`

**原因:** 存在しないプロパティやメソッドにアクセスしている

**解決方法:**
```python
def my_strategy(bt):
    # 利用可能なプロパティ
    bt.data             # 現在時点までのデータ (dict)
    bt.equity           # 現在の資産
    bt.cash             # 現在の現金
    bt.current_time     # 現在の日時
    bt.progress         # 進捗率（0.0〜1.0）
    bt.step_index       # 現在のステップインデックス
    bt.is_finished      # 完了フラグ
    bt.position         # 全銘柄合計ポジション
    bt.trades           # アクティブな取引
    bt.closed_trades    # 決済済み取引
    bt.orders           # 未約定の注文

    for code, df in bt.data.items():
        # 個別銘柄のポジション取得
        pos = bt.position_of(code)

        if pos == 0:
            bt.buy(code=code, tag="entry")
        elif pos > 0:
            bt.sell(code=code, tag="exit")
```

### 問題: 戦略が動作しない

**原因:** ロジックエラーまたはデータアクセスの問題

**解決方法:**
```python
def debug_strategy(bt):
    """デバッグ用の戦略"""
    for code, df in bt.data.items():
        print(f"銘柄: {code}")
        print(f"データ行数: {len(df)}")
        print(f"最新終値: {df['Close'].iloc[-1] if len(df) > 0 else 'N/A'}")
        print(f"ポジション: {bt.position_of(code)}")
        print(f"資産: {bt.equity:,.0f}")
        print("---")

        if len(df) >= 2:
            c0 = df['Close'].iloc[-2]
            c1 = df['Close'].iloc[-1]

            if bt.position_of(code) == 0 and c1 < c0:
                print(f"買い注文: {code}")
                bt.buy(code=code, tag="dip")

bt = Backtest(data={'TEST': df}, cash=10000)
bt.set_strategy(debug_strategy)

# 最初の10ステップだけ実行してデバッグ
bt.start()
for i in range(min(10, len(bt.index))):
    bt.step()
    print(f"ステップ {i+1} 完了\n")
```

## バックテスト実行の問題

### 問題: `ValueError: sizeは正の資産割合または正の整数単位である必要があります`

**原因:** 取引サイズが無効

**解決方法:**
```python
def my_strategy(bt):
    # 正しい: 資産割合（0-1の間）
    bt.buy(size=0.1)  # 10%の資産を使用

    # 正しい: 整数単位
    bt.buy(size=100)  # 100株

    # 間違った: 負の値
    # bt.buy(size=-100)  # エラー

    # 間違った: 1より大きい割合
    # bt.buy(size=1.5)  # エラー
```

### 問題: バックテストが終了しない

**原因:** 無限ループまたは非常に長い処理時間

**解決方法:**
```python
# 1. データサイズを確認
print(f"データサイズ: {len(data)}")

# 2. 戦略のロジックを簡素化して切り分け
def simple_strategy(bt):
    for code, df in bt.data.items():
        if len(df) == 1 and bt.position_of(code) == 0:
            bt.buy(code=code)

# 3. データ期間を短くする
short_data = data.tail(100)

bt = Backtest(data={'TEST': short_data}, cash=10000)
bt.set_strategy(simple_strategy)
results = bt.run()
```

### 問題: 結果が期待と異なる

**原因:** 戦略ロジック、データ、またはパラメータの問題

**解決方法:**
```python
# 1. データを確認
print("データの最初の5行:")
print(data.head())
print("データの最後の5行:")
print(data.tail())

# 2. 戦略の動作を確認
def logging_strategy(bt):
    """ロギング付き戦略"""
    for code, df in bt.data.items():
        if len(df) == 1 and bt.position_of(code) == 0:
            price = df['Close'].iloc[-1]
            bt.buy(code=code, tag="entry")
            print(f"買い注文: {code} @ {price}")

        if len(df) % 100 == 0:
            print(f"バー {len(df)}: 資産 {bt.equity:,.0f}, 現金 {bt.cash:,.0f}")

bt = Backtest(data={'TEST': data}, cash=10000, commission=0.001)
bt.set_strategy(logging_strategy)
results = bt.run()

# 3. パラメータを確認
print("バックテストパラメータ:")
print(f"現金残高: {bt.cash}")
print(f"手数料: {bt.commission}")
```

## パフォーマンスの問題

### 問題: バックテストが遅い

**原因:** 非効率な計算や大量のデータ

**解決方法:**
```python
# 1. データサイズを削減
short_data = data.tail(1000)  # 最新1000バーのみ使用

# 2. 事前計算でパフォーマンスを向上
data['SMA_20'] = data['Close'].rolling(20).mean()
data['SMA_50'] = data['Close'].rolling(50).mean()

bt = Backtest(data={'TEST': data}, cash=10000)

def optimized_strategy(bt):
    """事前計算された値を参照"""
    for code, df in bt.data.items():
        if len(df) < 50:
            continue

        sma20 = df['SMA_20'].iloc[-1]
        sma50 = df['SMA_50'].iloc[-1]

        if bt.position_of(code) == 0 and sma20 > sma50:
            bt.buy(code=code, tag="golden_cross")

bt.set_strategy(optimized_strategy)
results = bt.run()
```

### 問題: メモリ使用量が大きい

**原因:** 大量のデータまたは非効率なデータ構造

**解決方法:**
```python
# 1. データ型を最適化
data = data.astype({
    'Open': 'float32',
    'High': 'float32',
    'Low': 'float32',
    'Close': 'float32',
    'Volume': 'int32'
})

# 2. 不要な列を削除
data = data[['Open', 'High', 'Low', 'Close', 'Volume']]
```

## エラーメッセージ一覧

### よくあるエラーメッセージと解決方法

| エラーメッセージ | 原因 | 解決方法 |
|------------------|------|----------|
| `ModuleNotFoundError: No module named 'BackcastPro'` | インストールされていない | `pip install BackcastPro` |
| `TypeError: data[XXX] must be a pandas.DataFrame` | データがDataFrameでない | `pd.DataFrame(data)` |
| `ValueError: Some OHLC values are missing` | 欠損値がある | `data.dropna()` |
| `ValueError: sizeは正の資産割合または...` | 取引サイズが無効 | `size=0.1` または `size=100` |
| `RuntimeError: start() を呼び出してください` | バックテスト未開始 | `bt.start()` または `Backtest(data=...)` |
| `ValueError: 複数銘柄がある場合はcodeを指定してください` | 複数銘柄でcode未指定 | `bt.buy(code='7203.T')` |
| `requests.RequestException: Failed to fetch data` | API接続エラー | インターネット接続を確認 |

### デバッグのヒント

1. **ログを有効にする**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

2. **データを確認する**
```python
print("データ形状:", data.shape)
print("データ列:", data.columns.tolist())
print("欠損値:", data.isnull().sum())
```

3. **状態スナップショットを確認する**
```python
bt = Backtest(data={'TEST': data}, cash=10000)
bt.set_strategy(my_strategy)

# 10ステップ進める
bt.goto(10, strategy=my_strategy)

# 状態を確認
state = bt.get_state_snapshot()
print(state)
```

4. **エラーハンドリングを追加する**
```python
try:
    bt = Backtest(data={'TEST': data}, cash=10000)
    bt.set_strategy(my_strategy)
    results = bt.run()
except Exception as e:
    print(f"エラー: {e}")
    print(f"エラータイプ: {type(e).__name__}")
    import traceback
    traceback.print_exc()
```

## サポート

問題が解決しない場合は、以下の方法でサポートを受けることができます：

1. **GitHub Issues**: バグ報告や機能要求
2. **Discord**: コミュニティでの質問
3. **ドキュメント**: 詳細な使用方法の確認

## まとめ

このトラブルシューティングガイドでは、BackcastProを使用する際によく発生する問題とその解決方法を説明しました。問題が発生した場合は、まずこのガイドを確認し、適切な解決方法を試してください。
