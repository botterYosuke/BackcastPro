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

### 問題: `ImportError: cannot import name 'Strategy'`

**原因:** 古いバージョンがインストールされている、またはインストールが不完全

**解決方法:**
```powershell
# 既存のインストールをアンインストール
python -m pip uninstall BackcastPro -y

# 最新版を再インストール
python -m pip install BackcastPro
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

### 問題: `ValueError: data must be a pandas.DataFrame with columns`

**原因:** データが辞書形式でない、またはDataFrameでない

**解決方法:**
```python
# 正しい形式: 辞書で銘柄コードをキーとしてDataFrameを渡す
data = {
    '7203.JP': toyota_data,
    '6758.JP': sony_data
}
bt = Backtest(data, MyStrategy)

# 単一銘柄の場合も辞書形式で渡す
bt = Backtest({'7203.JP': toyota_data}, MyStrategy)
```

### 問題: `ValueError: data must be a pandas.DataFrame with columns` (旧形式)

**原因:** データがDataFrameでない、または必要な列がない

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

# 3. 手動でデータを設定
custom_data = pd.DataFrame({
    'Open': [100, 101, 102],
    'High': [105, 106, 107],
    'Low': [99, 100, 101],
    'Close': [104, 105, 106],
    'Volume': [1000, 1100, 1200]
}, index=pd.date_range('2023-01-01', periods=3))
```

### 問題: データが空または取得できない

**原因:** 銘柄コードが間違っている、または期間が無効

**解決方法:**
```python
import pandas_datareader.data as web

# 1. 期間を確認
from datetime import datetime, timedelta
end_date = datetime.now()
start_date = end_date - timedelta(days=365)
print(f"期間: {start_date} から {end_date}")

# 2. 異なる銘柄で試す
data = web.DataReader('7203.JP', 'stooq')  # トヨタ
if data is None or len(data) == 0:
    print("データが取得できませんでした")
```

## 戦略実装の問題

### 問題: `TypeError: strategy must be a Strategy sub-type`

**原因:** 戦略クラスがStrategyを継承していない

**解決方法:**
```python
from BackcastPro import Strategy

# 正しい実装
class MyStrategy(Strategy):  # Strategyを継承
    def init(self):
        pass
    
    def next(self):
        pass

# 間違った実装
class WrongStrategy:  # Strategyを継承していない
    def init(self):
        pass
    
    def next(self):
        pass
```

### 問題: `AttributeError: 'MyStrategy' object has no attribute 'data'`

**原因:** `init()`メソッドで`self.data`にアクセスしている

**解決方法:**
```python
class MyStrategy(Strategy):
    def init(self):
        # 正しい: self.dataを使用
        for code, df in self.data.items():
            df['SMA'] = df.Close.rolling(20).mean()
    
    def next(self):
        # 正しい: self.dataを使用
        for code, df in self.data.items():
            if df.SMA.iloc[-1] > df.Close.iloc[-1]:
                self.buy(code=code)
```

### 問題: 戦略が動作しない

**原因:** ロジックエラーまたはデータアクセスの問題

**解決方法:**
```python
class DebugStrategy(Strategy):
    def init(self):
        print("戦略初期化完了")
        print("データ形状:", self.data.shape)
        print("データ列:", self.data.columns.tolist())
    
    def next(self):
        for code, df in self.data.items():
            print(f"現在のバー: {len(df)}")
            print(f"現在の終値: {df.Close.iloc[-1]}")
            
            # デバッグ情報を出力
            if len(df) % 100 == 0:  # 100バーごとに出力
                print(f"エクイティ: {self.equity}")
                print(f"ポジション: {self.position.size}")
```

## バックテスト実行の問題

### 問題: `ValueError: sizeは正の資産割合または正の整数単位である必要があります`

**原因:** 取引サイズが無効

**解決方法:**
```python
class MyStrategy(Strategy):
    def next(self):
        # 正しい: 資産割合（0-1の間）
        self.buy(size=0.1)  # 10%の資産を使用
        
        # 正しい: 整数単位
        self.buy(size=100)  # 100株
        
        # 間違った: 負の値
        # self.buy(size=-100)  # エラー
        
        # 間違った: 1より大きい割合
        # self.buy(size=1.5)  # エラー
```

### 問題: バックテストが終了しない

**原因:** 無限ループまたは非常に長い処理時間

**解決方法:**
```python
# 1. データサイズを確認
print(f"データサイズ: {len(data)}")

# 2. 戦略のロジックを簡素化して切り分け
class SimpleStrategy(Strategy):
    def init(self):
        pass
    
    def next(self):
        for code, df in self.data.items():
            if len(df) == 1:
                self.buy(code=code)
                return

# 3. 長時間実行を避けるためにデータ期間を短くする
data = data.tail(2000)

bt = Backtest({'TEST': data}, SimpleStrategy)
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
class LoggingStrategy(Strategy):
    def init(self):
        self.trades = []
    
    def next(self):
        # 取引ログを記録
        for code, df in self.data.items():
            if len(df) == 1:
                self.buy(code=code)
                self.trades.append(('BUY', df.Close.iloc[-1]))
            
            # 定期的にログを出力
            if len(df) % 100 == 0:
                print(f"バー {len(df)}: エクイティ {self.equity}")

# 3. パラメータを確認
bt = Backtest({'TEST': data}, LoggingStrategy, cash=10000, commission=0.001)
print("バックテストパラメータ:")
print(f"初期資金: {bt._cash}")
print(f"手数料: {bt._commission}")
```

## パフォーマンスの問題

### 問題: バックテストが遅い

**原因:** 非効率な計算や大量のデータ

**解決方法:**
```python
# 1. データサイズを削減
data = data.tail(1000)  # 最新1000バーのみ使用

# 2. 計算を最適化
class OptimizedStrategy(Strategy):
    def init(self):
        # 事前計算でパフォーマンスを向上
        for code, df in self.data.items():
            df['SMA'] = df.Close.rolling(20).mean()
            df['RSI'] = calculate_rsi(df)
    
    def next(self):
        # 事前計算された値を参照
        for code, df in self.data.items():
            if df.SMA.iloc[-1] > df.Close.iloc[-1]:
                self.buy(code=code)

# 3. 不要な計算を削除
class SimpleStrategy(Strategy):
    def init(self):
        # 必要最小限の計算のみ
        pass
    
    def next(self):
        # シンプルなロジック
        for code, df in self.data.items():
            if len(df) == 1:
                self.buy(code=code)
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

# 3. データを分割して処理
chunk_size = 1000
for i in range(0, len(data), chunk_size):
    chunk = data.iloc[i:i+chunk_size]
    bt = Backtest({'CHUNK': chunk}, MyStrategy)
    results = bt.run()
```

## エラーメッセージ一覧

### よくあるエラーメッセージと解決方法

| エラーメッセージ | 原因 | 解決方法 |
|------------------|------|----------|
| `ModuleNotFoundError: No module named 'BackcastPro'` | インストールされていない | `pip install BackcastPro` |
| `TypeError: strategy must be a Strategy sub-type` | 戦略クラスがStrategyを継承していない | `class MyStrategy(Strategy):` |
| `ValueError: data must be a pandas.DataFrame` | データがDataFrameでない | `pd.DataFrame(data)` |
| `ValueError: Some OHLC values are missing` | 欠損値がある | `data.dropna()` |
| `ValueError: sizeは正の資産割合または正の整数単位である必要があります` | 取引サイズが無効 | `size=0.1` または `size=100` |
| `requests.RequestException: Failed to fetch data` | API接続エラー | インターネット接続を確認 |
| `AttributeError: 'MyStrategy' object has no attribute 'data'` | `init()`で`self.data`にアクセス | `init()`では`self.data`を使用可能 |

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

3. **戦略の動作を確認する**
```python
class DebugStrategy(Strategy):
    def init(self):
        print("戦略初期化")
    
    def next(self):
        for code, df in self.data.items():
            if len(df) % 100 == 0:
                print(f"バー {len(df)}: エクイティ {self.equity}")
```

4. **エラーハンドリングを追加する**
```python
try:
    bt = Backtest({'TEST': data}, MyStrategy)
    results = bt.run()
except Exception as e:
    print(f"エラー: {e}")
    print(f"エラータイプ: {type(e)}")
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
