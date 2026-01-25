# <img src="https://raw.githubusercontent.com/botterYosuke/BackcastPro/main/docs/img/logo.drawio.svg" alt="BackcastPro Logo" width="40" height="24"> BackcastPro

トレーディング戦略のためのPythonバックテストライブラリ。
**リプレイ型シミュレーター**で、1バーずつ時間を進めながらチャートと売買を可視化できます。

## インストール（Windows）

### PyPIから（エンドユーザー向け）

```powershell
python -m pip install BackcastPro
```

### 開発用インストール

```powershell
git clone <repository-url>
cd BackcastPro
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pip install -r requirements.txt
```

## 使用方法

### 基本的な使い方

```python
from BackcastPro import Backtest
import pandas as pd

# データ準備
df = pd.read_csv("AAPL.csv", index_col=0, parse_dates=True)
bt = Backtest(data={"AAPL": df}, cash=100000)

# 戦略関数
def my_strategy(bt):
    if bt.position == 0:
        bt.buy(tag="entry")
    elif bt.position > 0:
        bt.sell(tag="exit")

# ステップ実行
while not bt.is_finished:
    my_strategy(bt)
    bt.step()

# 結果を取得
results = bt.finalize()
print(results)
```

### 一括実行

```python
bt = Backtest(data={"AAPL": df}, cash=100000)
results = bt.run_with_strategy(my_strategy)
```

### marimo連携（リプレイ型シミュレーター）

```python
import marimo as mo

slider = mo.ui.slider(start=1, stop=len(bt.index), value=1, label="時間")
bt.goto(slider.value, strategy=my_strategy)
chart = bt.chart()  # plotlyローソク足 + 売買マーカー

mo.vstack([slider, chart])
```

## ドキュメント

- [ドキュメント一覧](https://github.com/botterYosuke/BackcastPro/blob/main/docs/index.md)

## バグ報告 / サポート

- バグ報告や要望は GitHub Issues へ
- 質問は Discord コミュニティへ（[招待リンク](https://discord.gg/fzJTbpzE)）
- 使い方はドキュメントをご参照ください
