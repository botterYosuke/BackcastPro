# <img src="img/logo.drawio.svg" alt="BackcastPro Logo" width="40" height="24"> チュートリアル

BackcastProを使ったバックテストの基本的な使い方を学びます。

## 目次

1. [インストール](#インストール)
2. [基本的な使い方](#基本的な使い方)
3. [最初の戦略](#最初の戦略)
4. [データの取得](#データの取得)
5. [バックテストの実行](#バックテストの実行)
6. [結果の解釈](#結果の解釈)
7. [次のステップ](#次のステップ)

## インストール（Windows）

```powershell
python -m pip install BackcastPro
```

## 基本的な使い方

BackcastProでは、バックテストの実行時に**TimeStomp管理**を使用して、各時点での戦略実行を行います。これにより、より正確な時系列での取引シミュレーションが可能になります。

```mermaid
sequenceDiagram
    participant U as User
    participant D as DataReader
    participant B as Backtest
    participant S as Strategy
    participant R as Results
    U->>D: DataReader('7203.JP', 'stooq')
    D-->>U: OHLCV DataFrame
    U->>B: Backtest({code: data}, Strategy)
    B->>S: init()
    loop 各タイムスタンプ
        B->>S: next(current_time)
        S->>B: buy()/sell()
    end
    B-->>R: pd.Series（統計含む）
```

### TimeStomp管理の特徴

- **正確な時系列処理**: 各タイムスタンプで戦略を実行
- **リアルタイム感覚**: 実際の取引に近いタイミングでの判断
- **プログレスバー表示**: バックテストの進行状況を視覚的に確認

### 1. 必要なライブラリのインポート

```python
from BackcastPro import Strategy, Backtest
import pandas as pd
```

### 2. データの準備

```python
# トヨタの株価データを取得
code='7203.JP'
df = web.DataReader(code, 'stooq')
print(df.head())
```

## 最初の戦略

### シンプルな買い持ち戦略

最初に、何もしない「買い持ち」戦略を作成してみましょう：

```python
class BuyAndHold(Strategy):
    def init(self):
        # 戦略の初期化（今回は何もしない）
        pass
    
    def next(self, current_time):
        # 最初のバーで一度だけ買い
        for code, df in self.data.items():
            if len(df) == 1:
                self.buy(code=code)
```

### バックテストの実行

```python
# バックテストを実行
bt = Backtest({code: data}, BuyAndHold, cash=10000, commission=0.001)
results = bt.run()
print(results)
```

## データの取得

### 日本株データの取得

```python
import pandas_datareader.data as web

# 特定の銘柄のデータを取得
toyota_data = web.DataReader('7203.JP', 'stooq') # トヨタ
sony_data = web.DataReader('6758.JP', 'stooq')   # ソニー

# 期間を指定してデータを取得
from datetime import datetime, timedelta

end_date = datetime.now()
start_date = end_date - timedelta(days=365)  # 1年前

data = web.DataReader('7203.JP', 'stooq', start_date, end_date)
```

### カスタムデータの使用

```python
import pandas as pd

# カスタムデータを作成
custom_data = pd.DataFrame({
    'Open': [100, 101, 102, 103, 104],
    'High': [105, 106, 107, 108, 109],
    'Low': [99, 100, 101, 102, 103],
    'Close': [104, 105, 106, 107, 108],
    'Volume': [1000, 1100, 1200, 1300, 1400]
}, index=pd.date_range('2023-01-01', periods=5))

# バックテストで使用
bt = Backtest({'CUSTOM': custom_data}, BuyAndHold)
results = bt.run()
```

### 複数銘柄の同時バックテスト

```python
# 複数の銘柄データを取得
toyota_data = web.DataReader('7203.JP', 'stooq')
sony_data = web.DataReader('6758.JP', 'stooq')

# 複数銘柄でバックテストを実行
multi_data = {
    '7203.JP': toyota_data,
    '6758.JP': sony_data
}

bt = Backtest(multi_data, BuyAndHold, cash=10000)
results = bt.run()
```

## バックテストの実行

```python
bt = Backtest(
    {code: data},
    BuyAndHold,
    cash=10000,
    commission=0.001,
    finalize_trades=True,
)
results = bt.run()
```

> 複数戦略の比較や最適化の例は `examples/` と「高度な使い方」を参照してください。

## 結果の解釈

### 基本的な統計情報

```python
results = bt.run()

# 主要な統計情報を表示
print(f"総リターン: {results['Return [%]']:.2f}%")
print(f"年率リターン: {results['Return (Ann.) [%]']:.2f}%")
print(f"シャープレシオ: {results['Sharpe Ratio']:.2f}")
print(f"最大ドローダウン: {results['Max. Drawdown [%]']:.2f}%")
print(f"取引回数: {results['# Trades']}")
print(f"勝率: {results['Win Rate [%]']:.2f}%")
```

### エクイティカーブの確認

```python
# エクイティカーブを取得
equity_curve = results['_equity_curve']
print(equity_curve.head())

# ドローダウンを確認
drawdown = equity_curve['DrawdownPct']
print(f"最大ドローダウン: {drawdown.min():.2f}%")
```

### トレード履歴の確認

```python
# トレード履歴を取得
trades = results['_trades']
print(trades.head())

# 勝ちトレードと負けトレードを分析
winning_trades = trades[trades['PnL'] > 0]
losing_trades = trades[trades['PnL'] < 0]

print(f"勝ちトレード数: {len(winning_trades)}")
print(f"負けトレード数: {len(losing_trades)}")
print(f"平均勝ち: {winning_trades['PnL'].mean():.2f}")
print(f"平均負け: {losing_trades['PnL'].mean():.2f}")
```

## 次のステップ

### 1. より複雑な戦略の実装

```python
class MovingAverageCross(Strategy):
    def init(self):
        # 移動平均を計算
        for code, df in self.data.items():
            df['SMA_short'] = df.Close.rolling(10).mean()
            df['SMA_long'] = df.Close.rolling(20).mean()
    
    def next(self, current_time):
        # ゴールデンクロスで買い、デッドクロスで売り
        for code, df in self.data.items():
            if (df.SMA_short.iloc[-1] > df.SMA_long.iloc[-1] and
                df.SMA_short.iloc[-2] <= df.SMA_long.iloc[-2]):
                self.buy(code=code)
            
            elif (df.SMA_short.iloc[-1] < df.SMA_long.iloc[-1] and
                  df.SMA_short.iloc[-2] >= df.SMA_long.iloc[-2]):
                self.sell(code=code)
```

### 2. リスク管理の追加

`buy()` / `sell()` の `sl` と `tp` を活用できます（詳細は API リファレンス参照）。

### 3. パフォーマンスの可視化

```python
import matplotlib.pyplot as plt

# エクイティカーブをプロット
equity_curve = results['_equity_curve']
plt.figure(figsize=(12, 6))
plt.subplot(2, 1, 1)
plt.plot(equity_curve.index, equity_curve['Equity'])
plt.title('エクイティカーブ')
plt.ylabel('資産')

plt.subplot(2, 1, 2)
plt.plot(equity_curve.index, equity_curve['DrawdownPct'])
plt.title('ドローダウン')
plt.ylabel('ドローダウン (%)')
plt.xlabel('日付')

plt.tight_layout()
plt.show()
```

### 4. Streamlitでの可視化

```python
# Streamlitアプリの作成
import streamlit as st

st.title('バックテスト結果')
st.write('戦略:', 'MovingAverageCross')
st.write('総リターン:', f"{results['Return [%]']:.2f}%")

# エクイティカーブを表示
st.line_chart(equity_curve[['Equity']])

# トレード履歴を表示
st.dataframe(trades)
```

## よくある質問

### Q: データが取得できない場合はどうすればいいですか？

A: 以下の点を確認してください：
1. インターネット接続
2. 銘柄コードの正確性
3. 日付範囲の妥当性

### Q: バックテストが遅い場合はどうすればいいですか？

A: 以下の方法を試してください：
1. データ期間を短くする
2. 複雑な計算を`init()`で事前計算する
3. 不要なデータを削除する

### Q: 結果が期待と異なる場合はどうすればいいですか？

A: 以下の点を確認してください：
1. データの品質
2. 戦略ロジックの正確性
3. パラメータ設定の妥当性

## まとめ

- インストール → データ取得 → 戦略実装 → 実行 → 分析、の順に進めます
- 詳細は「APIリファレンス」「高度な使い方」「サンプルコード」を参照してください
