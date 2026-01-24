# BackcastPro リプレイ型シミュレーター 変更プラン

## 概要

**目的**: バックテスト結果ではなく「戦略が意思決定した瞬間のチャート体験」を提供する

現在の `Backtest.run()` は全期間を一括実行して結果だけを返す設計です。
marimo と連携して、**1バーずつ時間を進めながらチャートと売買を可視化**できるリプレイ型シミュレーターに変更します。

### 設計決定事項
- **チャート**: plotly（ローソク足 + 売買マーカー）
- **UI**: スライダー + 再生ボタンの両方
- **銘柄**: 複数銘柄対応

---

## 1. なぜ既存バックテストが分かりにくいか

```
従来のバックテスト:
  for bar in all_bars:     ← 一気に消化
      strategy.next()
  return results           ← 結果だけ

問題点:
  「判断した瞬間のチャート文脈」が完全に失われる
```

---

## 2. 目標アーキテクチャ

```
[ 全OHLCデータ (dict[code, DataFrame]) ]
                |
                v
[ 現在のindex (t) ] ← marimo UI が制御（スライダー / 再生ボタン）
                |
                v
[ data[:t] ] → チャート描画（plotly）
                |
                v
[ strategy(bt) ] → 売買判断（bt.buy() / bt.sell()）
                |
                v
[ trades / position / cash / equity ]
```

---

## 3. 約定タイミングモデル（重要）

```
┌─────────────────────────────────────────────────────────────┐
│  時間軸: ... │ t-2 │ t-1 │  t  │ t+1 │ ...                 │
│              │     │     │     │     │                     │
│  step(t)実行時:                                            │
│    1. data[:t] が確定（t の OHLC が見える）               │
│    2. strategy(bt) が呼ばれる                              │
│       → t の Close まで見て判断                           │
│    3. buy()/sell() で注文を発行                           │
│    4. bt.step() で broker.next(t) が実行                  │
│       → 注文は t の価格で約定（trade_on_close=True時）    │
│       → または t+1 の Open で約定（デフォルト）           │
└─────────────────────────────────────────────────────────────┘

【ルール】
- strategy は「確定足（t）まで」を見て判断する
- 注文は step() 内で処理される
- trade_on_close=False（デフォルト）: 次足始値で約定
- trade_on_close=True: 現在足終値で約定
```

---

## 4. 目標の使用イメージ

### 4.1 基本的な使い方

```python
import marimo as mo
from BackcastPro import Backtest

# データ準備（複数銘柄対応）
bt = Backtest(
    data={"AAPL": df_aapl, "GOOG": df_goog},
    cash=100000
)

# 戦略関数（外部で定義）
def my_strategy(bt):
    # ⚠️ 複数銘柄時は position_of() を使う
    df = bt.data["AAPL"]
    if len(df) < 2:
        return

    c0 = df["Close"].iloc[-2]
    c1 = df["Close"].iloc[-1]

    pos = bt.position_of("AAPL")  # ← position ではなく position_of を使用

    if pos == 0 and c1 < c0:
        bt.buy(code="AAPL", tag="dip_buy")  # tag で理由を記録
    elif pos > 0 and c1 > c0:
        bt.sell(code="AAPL", tag="profit_take")

# 1ステップ進める
def step(bt):
    my_strategy(bt)
    bt.step()
```

### 4.2 marimo UIとの連携（スライダー主体）

```python
# 時間制御スライダー
slider = mo.ui.slider(
    start=1,
    stop=len(bt.index),
    value=1,
    label="時間"
)

# スライダー値に応じてバックテストを進める（戦略付き）
bt.goto(slider.value, strategy=my_strategy)

# チャート描画
chart = bt.chart(code="AAPL")
mo.vstack([slider, chart])
```

### 4.3 marimo UIとの連携（自動再生）

```python
# 再生状態
is_playing, set_playing = mo.state(False)

# 現在位置（slider とは独立）
current_step, set_step = mo.state(1)

# 再生/停止ボタン
play_btn = mo.ui.button(
    label="▶ 再生" if not is_playing else "⏸ 停止",
    on_click=lambda _: set_playing(not is_playing)
)

# 自動再生（slider は同期させない）
def auto_advance(_):
    if is_playing and current_step < len(bt.index):
        bt.goto(current_step + 1, strategy=my_strategy)
        set_step(current_step + 1)

refresh = mo.ui.refresh(
    default_interval="500ms",
    on_change=auto_advance
)

# 現在位置の表示（slider ではなくテキスト）
mo.md(f"**Step: {current_step} / {len(bt.index)}**")

mo.vstack([
    mo.hstack([play_btn, slider]),
    chart,
    refresh if is_playing else None
])
```

---

## 5. Backtest クラスの変更内容

### 5.1 `__init__` の変更

```python
import sys
from typing import Optional, Tuple, Union, List, Callable
import numpy as np
import pandas as pd
import plotly.graph_objects as go

class Backtest:
    def __init__(self,
                data: dict[str, pd.DataFrame] = None,
                *,
                cash: float = 10_000,
                spread: float = .0,
                commission: Union[float, Tuple[float, float]] = .0,
                margin: float = 1.,
                trade_on_close=False,
                hedging=False,
                exclusive_orders=False,
                finalize_trades=False,
                ):
        # strategy 引数を削除

        # 既存のバリデーション...
        self.set_data(data)

        self._broker_factory = partial(
            _Broker, cash=cash, spread=spread, commission=commission,
            margin=margin, trade_on_close=trade_on_close, hedging=hedging,
            exclusive_orders=exclusive_orders
        )

        # ステップ実行用の状態管理
        self._broker_instance: Optional[_Broker] = None
        self._step_index = 0
        self._is_started = False
        self._is_finished = False
        self._current_data: dict[str, pd.DataFrame] = {}
        self._results: Optional[pd.Series] = None
        self._finalize_trades = bool(finalize_trades)

        # パフォーマンス最適化: 各銘柄の index position マッピング
        self._index_positions: dict[str, dict] = {}

        # 自動的にstart()を呼び出す
        if data is not None:
            self.start()
```

### 5.2 `start()` メソッド

```python
def start(self) -> 'Backtest':
    """バックテストを開始準備する"""
    if self._data is None:
        raise ValueError("data が設定されていません")

    self._broker_instance = self._broker_factory(data=self._data)
    self._step_index = 0
    self._is_started = True
    self._is_finished = False
    self._current_data = {}
    self._results = None

    # パフォーマンス最適化: 各銘柄の index → position マッピングを事前計算
    self._index_positions = {}
    for code, df in self._data.items():
        self._index_positions[code] = {
            ts: i for i, ts in enumerate(df.index)
        }

    return self
```

### 5.3 `step()` メソッド（パフォーマンス最適化版）

```python
def step(self) -> bool:
    """
    1ステップ（1バー）進める。

    【タイミング】
    - step(t) 実行時、data[:t] が見える状態になる
    - 注文は broker.next(t) 内で処理される
    """
    if not self._is_started:
        raise RuntimeError("start() を呼び出してください")

    if self._is_finished:
        return False

    if self._step_index >= len(self.index):
        self._is_finished = True
        return False

    current_time = self.index[self._step_index]

    with np.errstate(invalid='ignore'):
        # パフォーマンス最適化: iloc ベースで slicing
        for code, df in self._data.items():
            if current_time in self._index_positions[code]:
                pos = self._index_positions[code][current_time]
                self._current_data[code] = df.iloc[:pos + 1]
            # current_time がこの銘柄に存在しない場合は前の状態を維持

        # ブローカー処理（注文の約定）
        try:
            self._broker_instance._data = self._current_data
            self._broker_instance.next(current_time)
        except Exception:
            self._is_finished = True
            return False

    self._step_index += 1

    if self._step_index >= len(self.index):
        self._is_finished = True

    return not self._is_finished
```

### 5.4 `goto()` メソッド（戦略付き対応）

```python
def goto(self, step: int, strategy: Callable[['Backtest'], None] = None) -> 'Backtest':
    """
    指定ステップまで進める（スライダー連携用）

    Args:
        step: 目標のステップ番号（1-indexed）
        strategy: 各ステップで呼び出す戦略関数（省略可）
    """
    step = max(1, min(step, len(self.index)))

    # 現在より前に戻る場合はリセット
    if step < self._step_index:
        self.reset()

    # 目標まで進める（戦略を適用しながら）
    while self._step_index < step and not self._is_finished:
        if strategy:
            strategy(self)
        self.step()

    return self

def reset(self) -> 'Backtest':
    """バックテストをリセットして最初から"""
    self._broker_instance = self._broker_factory(data=self._data)
    self._step_index = 0
    self._is_finished = False
    self._current_data = {}
    return self
```

### 5.5 `buy()` / `sell()` メソッド（tag 対応）

```python
def buy(self, *,
        code: str = None,
        size: float = None,
        limit: Optional[float] = None,
        stop: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        tag: object = None) -> 'Order':
    """
    買い注文を発注する。

    Args:
        code: 銘柄コード（1銘柄のみの場合は省略可）
        size: 注文数量（省略時は利用可能資金の99.99%）
        tag: 注文理由（例: "dip_buy", "breakout"）→ チャートに表示可能
    """
    if not self._is_started:
        raise RuntimeError("start() を呼び出してください")

    if code is None:
        if len(self._data) == 1:
            code = list(self._data.keys())[0]
        else:
            raise ValueError("複数銘柄がある場合はcodeを指定してください")

    if size is None:
        size = 1 - sys.float_info.epsilon

    return self._broker_instance.new_order(code, size, limit, stop, sl, tp, tag)

def sell(self, *,
         code: str = None,
         size: float = None,
         limit: Optional[float] = None,
         stop: Optional[float] = None,
         sl: Optional[float] = None,
         tp: Optional[float] = None,
         tag: object = None) -> 'Order':
    """売り注文を発注する"""
    if not self._is_started:
        raise RuntimeError("start() を呼び出してください")

    if code is None:
        if len(self._data) == 1:
            code = list(self._data.keys())[0]
        else:
            raise ValueError("複数銘柄がある場合はcodeを指定してください")

    if size is None:
        size = 1 - sys.float_info.epsilon

    return self._broker_instance.new_order(code, -size, limit, stop, sl, tp, tag)
```

### 5.6 `chart()` メソッド（tag 表示対応）

```python
def chart(self, code: str = None, height: int = 500, show_tags: bool = True) -> go.Figure:
    """
    現在時点までのローソク足チャートを生成（売買マーカー付き）

    Args:
        code: 銘柄コード
        height: チャートの高さ
        show_tags: 売買理由（tag）をチャートに表示するか
    """
    if code is None:
        if len(self._data) == 1:
            code = list(self._data.keys())[0]
        else:
            raise ValueError("複数銘柄がある場合はcodeを指定してください")

    if code not in self._current_data or len(self._current_data[code]) == 0:
        return go.Figure()

    df = self._current_data[code]

    fig = go.Figure()

    # ローソク足
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name=code
    ))

    # 売買マーカー
    for trade in self._broker_instance.closed_trades + self._broker_instance.trades:
        if trade.code != code:
            continue

        is_long = trade.size > 0

        # エントリーマーカー
        hover_text = f"{'BUY' if is_long else 'SELL'}<br>Price: {trade.entry_price:.2f}"
        if show_tags and trade.tag:
            hover_text += f"<br>Reason: {trade.tag}"

        fig.add_trace(go.Scatter(
            x=[trade.entry_time],
            y=[trade.entry_price],
            mode="markers+text" if show_tags and trade.tag else "markers",
            marker=dict(
                color="green" if is_long else "red",
                size=12,
                symbol="triangle-up" if is_long else "triangle-down",
            ),
            text=[trade.tag] if show_tags and trade.tag else None,
            textposition="top center" if is_long else "bottom center",
            textfont=dict(size=10),
            hovertext=hover_text,
            hoverinfo="text",
            name="BUY" if is_long else "SELL",
            showlegend=False
        ))

        # イグジットマーカー（決済済みの場合）
        if trade.exit_time is not None:
            pnl = (trade.exit_price - trade.entry_price) * trade.size
            fig.add_trace(go.Scatter(
                x=[trade.exit_time],
                y=[trade.exit_price],
                mode="markers",
                marker=dict(
                    color="blue",
                    size=10,
                    symbol="x",
                ),
                hovertext=f"EXIT<br>Price: {trade.exit_price:.2f}<br>PnL: {pnl:+.2f}",
                hoverinfo="text",
                name="EXIT",
                showlegend=False
            ))

    fig.update_layout(
        title=f"{code} - {self.current_time}",
        xaxis_title="Date",
        yaxis_title="Price",
        height=height,
        xaxis_rangeslider_visible=False,
    )

    return fig
```

### 5.7 プロパティ

```python
@property
def data(self) -> dict[str, pd.DataFrame]:
    """現在時点までのデータ"""
    return self._current_data

@property
def position(self) -> int:
    """
    現在のポジションサイズ（全銘柄合計）

    ⚠️ 注意: 複数銘柄を扱う場合は position_of(code) を使用してください。
    このプロパティは後方互換性のために残されています。
    """
    if not self._is_started or self._broker_instance is None:
        return 0
    return self._broker_instance.position.size

def position_of(self, code: str) -> int:
    """
    指定銘柄のポジションサイズ（推奨）

    Args:
        code: 銘柄コード

    Returns:
        int: ポジションサイズ（正: ロング、負: ショート、0: ノーポジ）
    """
    if not self._is_started or self._broker_instance is None:
        return 0
    return sum(t.size for t in self._broker_instance.trades if t.code == code)

@property
def equity(self) -> float:
    """現在の資産"""
    if not self._is_started or self._broker_instance is None:
        return self._broker_factory.keywords.get('cash', 0)
    return self._broker_instance.equity

@property
def cash(self) -> float:
    """現在の現金残高"""
    if not self._is_started or self._broker_instance is None:
        return self._broker_factory.keywords.get('cash', 0)
    return self._broker_instance.cash

@property
def is_finished(self) -> bool:
    """完了したかどうか"""
    return self._is_finished

@property
def current_time(self) -> pd.Timestamp:
    """現在の日時"""
    if self._step_index == 0:
        return None
    return self.index[self._step_index - 1]

@property
def progress(self) -> float:
    """進捗率（0.0〜1.0）"""
    if len(self.index) == 0:
        return 0.0
    return self._step_index / len(self.index)

@property
def trades(self) -> list:
    """アクティブな取引リスト"""
    if not self._is_started or self._broker_instance is None:
        return []
    return list(self._broker_instance.trades)

@property
def closed_trades(self) -> list:
    """決済済み取引リスト"""
    if not self._is_started or self._broker_instance is None:
        return []
    return list(self._broker_instance.closed_trades)

@property
def orders(self) -> list:
    """未約定の注文リスト"""
    if not self._is_started or self._broker_instance is None:
        return []
    return list(self._broker_instance.orders)
```

### 5.8 `finalize()` と `run()` メソッド

```python
def finalize(self) -> pd.Series:
    """統計を計算して結果を返す"""
    if self._results is not None:
        return self._results

    if not self._is_started:
        raise RuntimeError("バックテストが開始されていません")

    broker = self._broker_instance

    if self._finalize_trades:
        for trade in reversed(broker.trades):
            trade.close()
        if self._step_index > 0:
            broker.next(self.index[self._step_index - 1])

    equity = pd.Series(broker._equity).bfill().fillna(broker._cash).values
    self._results = compute_stats(
        trades=broker.closed_trades,
        equity=np.array(equity),
        index=self.index[:self._step_index],
        strategy_instance=None,
        risk_free_rate=0.0,
    )

    return self._results

def run(self, strategy_func: Callable[['Backtest'], None] = None) -> pd.Series:
    """
    バックテストを最後まで実行（従来互換）

    Args:
        strategy_func: 各ステップで呼び出す関数 (bt) -> None
    """
    if not self._is_started:
        self.start()

    while not self._is_finished:
        if strategy_func:
            strategy_func(self)
        self.step()

    return self.finalize()
```

---

## 6. 完全なmarimo連携サンプル

```python
import marimo as mo
import pandas as pd
from BackcastPro import Backtest

# === セル1: データ準備 ===
df_aapl = pd.read_csv("AAPL.csv", index_col=0, parse_dates=True)
df_goog = pd.read_csv("GOOG.csv", index_col=0, parse_dates=True)

bt = Backtest(
    data={"AAPL": df_aapl, "GOOG": df_goog},
    cash=100000
)

# === セル2: 戦略定義 ===
def my_strategy(bt):
    """
    シンプルな戦略: 前日比下落で買い、上昇で売り

    【タイミング】
    - bt.data には current_time までの確定足が入っている
    - buy()/sell() の注文は次の step() で処理される
    """
    df = bt.data.get("AAPL")
    if df is None or len(df) < 2:
        return

    c0 = df["Close"].iloc[-2]
    c1 = df["Close"].iloc[-1]

    # ⚠️ 複数銘柄時は position ではなく position_of を使う
    pos = bt.position_of("AAPL")

    if pos == 0 and c1 < c0:
        bt.buy(code="AAPL", tag="dip_buy")
    elif pos > 0 and c1 > c0:
        bt.sell(code="AAPL", tag="profit_take")

# === セル3: UI コントロール ===
# 時間スライダー
slider = mo.ui.slider(
    start=1,
    stop=len(bt.index),
    value=1,
    label="📅 時間",
    show_value=True
)

# 銘柄選択
stock_select = mo.ui.dropdown(
    options=list(bt._data.keys()),
    value=list(bt._data.keys())[0],
    label="📈 銘柄"
)

mo.hstack([slider, stock_select])

# === セル4: バックテスト実行 & チャート ===
# スライダー位置まで進める（戦略を適用しながら）
bt.goto(slider.value, strategy=my_strategy)

# チャート描画（tag 表示付き）
chart = bt.chart(code=stock_select.value, height=500, show_tags=True)

# 情報パネル
info = mo.md(f"""
### 📊 状況
| 項目 | 値 |
|------|-----|
| 日時 | {bt.current_time} |
| 進捗 | {bt.progress * 100:.1f}% ({bt._step_index}/{len(bt.index)}) |
| 資産 | ${bt.equity:,.2f} |
| 現金 | ${bt.cash:,.2f} |
| ポジション({stock_select.value}) | {bt.position_of(stock_select.value)} 株 |
| 決済済取引 | {len(bt.closed_trades)} 件 |
""")

mo.vstack([chart, info])

# === セル5: 自動再生（オプション） ===
is_playing, set_playing = mo.state(False)

play_btn = mo.ui.button(
    label="▶ 再生" if not is_playing else "⏸ 停止",
    on_click=lambda _: set_playing(not is_playing)
)

# 注意: 自動再生中は slider とは独立して進む
# slider は「任意の位置にジャンプ」用として残す

play_btn
```

---

## 7. 実装の優先順位

### Phase 1: 最小実装（必須）
- [ ] `start()`, `step()`, `reset()` メソッド
- [ ] `buy()`, `sell()` メソッド（tag 対応）
- [ ] `data`, `position`, `position_of()`, `equity`, `current_time` プロパティ
- [ ] `is_finished`, `progress` プロパティ
- [ ] パフォーマンス最適化（iloc ベース slicing）

### Phase 2: 可視化（必須）
- [ ] `chart()` メソッド（plotly + tag 表示）
- [ ] `goto()` メソッド（strategy 引数対応）

### Phase 3: 互換性
- [ ] `run()` メソッド（従来の一括実行）
- [ ] `finalize()` メソッド（統計計算）

---

## 8. ファイル変更一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/BackcastPro/backtest.py` | `__init__`変更、新メソッド群の追加 |
| `tests/test_backtest_replay.py` | 新規：リプレイ機能のテスト |
| `examples/marimo_replay.py` | 新規：marimoサンプルノートブック |

---

## 9. 注意点（設計上の制約）

### (1) これは「評価用」であり「高速バックテスト」ではない
- 可視化付きなので数万バーは重い
- 全期間の高速評価は別途 `run()` でバッチ実行

### (2) `goto()` の実装について
- 過去に戻る場合はリセットして再実行が必要
- 将来的にはスナップショット機能で高速化可能

### (3) 約定モデル
- `trade_on_close=False`（デフォルト）: 次足始値で約定
- `trade_on_close=True`: 現在足終値で約定
- 視覚検証では簡略化で割り切る

### (4) `position` プロパティの注意
- 全銘柄合計のため、複数銘柄時は `position_of(code)` を使用すること
- ドキュメントで明示

### (5) marimo 自動再生の制限
- slider の値は直接変更できないため、自動再生時は slider と独立動作
- slider は「任意位置へのジャンプ」用として残す

---

## 10. 後続タスク

- [ ] Phase 1 の実装
- [ ] Phase 2 の実装
- [ ] ユニットテストの作成
- [ ] marimoサンプルノートブックの作成
