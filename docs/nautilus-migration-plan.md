# BackcastPro → NautilusTrader バックテストエンジン移行

## 実装状況（2026-02-22 更新）

| フェーズ | 内容 | 状態 |
|---|---|---|
| Phase 0 | bridge.py バグ修正 | ✅ 完了 |
| Phase 1 | nautilus_adapter.py 実装 + ユニットテスト（38/38 通過） | ✅ 完了 |
| Phase 2 | 各ファイルのインポート切り替え | ✅ 完了 |
| Phase 3 | 統合テスト（ユーザーによるアプリ動作確認） | ⏳ 未実施 |
| 追加作業 | `run(strategy, step_callback)` API 追加 + blacksheep.py の run 方式移行 | ⚠️ 要確認（後述） |

---

## 実装で判明した知見・設計思想・Tips

### 1. OHLC 整数丸め問題（実装で初めて発覚）

NautilusTrader の `Bar` は `low <= open` かつ `low <= close` を厳格にバリデーションする。
日本株データを整数円に丸める際、丸め誤差で制約が破られることがある。

**対処**: `ohlcv_to_bars()` で丸め後に制約を強制する。

```python
o = max(1, int(round(float(row["Open"]))))
h = max(1, int(round(float(row["High"]))))
lo = max(1, int(round(float(row["Low"]))))
c = max(1, int(round(float(row["Close"]))))
h = max(h, o, c)   # High は常に最大値
lo = min(lo, o, c) # Low は常に最小値
```

### 2. Equity の計算方法（PoC結果通り）

`balance_total(JPY)` はキャッシュ残高**のみ**を返す（ポジションのMTMを含まない）。
真のエクイティは自前で計算する必要がある：

```python
account = engine.portfolio.account(VENUE)
cash = float(account.balance_total(JPY).as_decimal())
for pos in engine.cache.positions_open():
    price = current_close_of(pos.instrument_id.symbol.value)
    cash += float(pos.signed_qty) * price
```

### 3. `commission` の適用方法

`MakerTakerFeeModel()` を Venue に設定し、Equity の `maker_fee` / `taker_fee` フィールドに手数料率（Decimal）を設定する。

```python
# add_venue 時
fee_model=MakerTakerFeeModel() if commission > 0 else None

# Equity 作成時
maker_fee=Decimal(str(commission)),
taker_fee=Decimal(str(commission)),
```

commission=0 の場合は `fee_model=None`（引数省略ではなく明示的に None を渡す）。

### 4. `price_precision` は `price_increment.precision` と一致させる

`Equity` 初期化時に `price_precision` と `price_increment` の精度が一致しないと `ValueError` になる。
日本株（整数円）の場合は `price_precision=0`、`price_increment=Price.from_str("1")`。

```python
# 正しい
Equity(price_precision=0, price_increment=Price.from_str("1"), ...)

# NG: precision=1 だが increment は整数
Equity(price_precision=1, price_increment=Price.from_str("1"), ...)  # ValueError
```

### 5. `StrategyConfig` の `order_id_tag` は必須

`Strategy` サブクラスを作る際、`StrategyConfig` に `order_id_tag` を設定しないと
エンジンがストラテジーを識別できない。

```python
class _InteractiveStrategyConfig(StrategyConfig, frozen=True):
    pass

super().__init__(_InteractiveStrategyConfig(order_id_tag="001"))
```

### 6. `goto()` での戦略スキップ

`goto()` 中は `_strategy_fn = None` にして高速実行する設計。
これにより SMA 等の計算が走らず goto がフレーム単位で速くなる。
ただし**戦略が累積状態を持つ場合**（例: 学習系モデル）は注意が必要。

```python
def goto(self, step, strategy=None):
    ...
    saved_fn = self._strategy_fn
    self._strategy_fn = None  # goto 中は戦略をスキップ
    try:
        while self._step_index < step and not self._is_finished:
            self.step()
    finally:
        self._strategy_fn = saved_fn  # 必ず復元
```

### 7. `BankruptError` の挙動の変更点

BackcastPro の `step()` は内部で `BankruptError` を **catch して False を返す**（re-raise しない）。
NautilusBacktest では game_setup.py の catch ブロックを活かすため **raise する** 設計に変更した。

```python
# NautilusBacktest.step() の末尾
if self.equity <= 0:
    self._is_finished = True
    raise BankruptError(...)  # BackcastProと違い、re-raiseする
```

game_setup.py の `step()` がこれを catch して `FAIL_003` スキルを発火させる（既存動作を維持）。

### 8. テストデータの注意点

合成データで `pd.date_range(..., freq="B")` （営業日）を使う点に注意。
`freq="D"` にすると土日が含まれ、実際の株価データとの挙動差が出やすい。

### 9. `run()` の API 拡張 — `strategy` と `step_callback` 引数（2026-02-22 追加）

NautilusTrader チュートリアルの「strategy を登録して `engine.run()` を1回呼ぶ」方式に合わせるため、
`NautilusBacktest.run()` に2つのオプション引数を追加した。

```python
# nautilus_adapter.py — 変更後の run()
def run(self, strategy=None, step_callback=None) -> pd.Series:
    """全バーを実行して統計を返す"""
    if strategy is not None:
        self.set_strategy(strategy)
    while not self._is_finished:
        self.step()
        if step_callback is not None:
            step_callback(self)
    return self.finalize()
```

**設計ポイント**:
- `strategy` を渡すと `set_strategy()` を内部で呼ぶ → 呼び出し側で別途 `set_strategy()` 不要
- `step_callback` は `step()` 完了後（注文執行済み）に呼ばれる → チャート更新タイミングが旧ループと同一
- 既存の `run()` との後方互換性あり（引数なしで呼べば従来通り動作）

**blacksheep.py での使用例**:
```python
def strategy(bt):
    _df = bt.data[code]
    if len(_df) < long_window + 1:
        return
    sma_short = _df.Close.rolling(short_window).mean()
    sma_long  = _df.Close.rolling(long_window).mean()
    prev_short, curr_short = sma_short.iloc[-2], sma_short.iloc[-1]
    prev_long,  curr_long  = sma_long.iloc[-2],  sma_long.iloc[-1]
    pos = bt.position_of(code)
    if prev_short <= prev_long and curr_short > curr_long and pos == 0:
        bt.buy(code=code)
    elif prev_short >= prev_long and curr_short < curr_long and pos > 0:
        bt.sell(code=code, size=pos)

try:
    bt.run(strategy=strategy, step_callback=update_all_backtest_charts)
except BankruptError:
    update_all_backtest_charts(bt)
```

旧方式 `for i in range(200): if not bt.step(): break` との比較：

| 項目 | 旧ループ方式 | run 方式 |
|------|------------|----------|
| 最大ステップ | 200回 | 全データ消費まで（上限なし） |
| 戦略の位置 | ループ内インライン | `strategy()` 関数として分離 |
| チャート更新 | `step()` 後に明示呼び出し | `step_callback` で自動呼び出し |
| BankruptError | ループの try/except | `run()` の try/except |

### 10. ⚠️ marimo ノートブックが読む `nautilus_adapter.py` の場所問題

`blacksheep.py`（`C:\Users\sasai\AppData\Roaming\marimo\notebooks\`）で実行時に以下のエラーが発生した：

```
TypeError: NautilusBacktest.run() got an unexpected keyword argument 'strategy'
```

編集したファイルは `C:\Users\sasai\Documents\marimo\src-tauri\resources\files\nautilus_adapter.py` だが、
marimo ノートブックが **別の場所の `nautilus_adapter.py`** を import している可能性がある。

**調査すべき場所**:
- `C:\Users\sasai\AppData\Roaming\marimo\notebooks\nautilus_adapter.py`（ノートブックと同じディレクトリ）
- Python の `sys.path` に含まれるどこか

> [!IMPORTANT]
> `nautilus_adapter.py` の編集後はノートブック側の Python プロセスを再起動しないと変更が反映されない場合がある（Python のモジュールキャッシュ）。
> marimo の場合は `mo.restart_kernel()` またはサーバー再起動が必要。
> また、**ノートブックファイルと同じディレクトリに `nautilus_adapter.py` が存在する場合、そちらが優先される**ため、
> 複数の場所に同名ファイルが存在しないか確認すること。

---

BackcastProのバックテストエンジンをNautilusTraderに置き換える。データ取得部分（[get_stock_daily](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/game_setup.py#161-170)等）はBackcastProを継続利用。ゲームUI（`bt.step()`, `bt.buy()`, `bt.chart()`のインターフェース）は維持する。

## PoC 検証結果

> [!NOTE]
> [poc_result.md](poc_result.md) で3方式を実機検証済み（nautilus_trader 1.221.0）。

| 方式 | 内容 | 結果 |
|------|------|------|
| A: `run(start=ts, end=ts)` | start/end フィルタで1バー実行 | ❌ Strategy が step 2 以降のバーを受け取らない |
| B: streaming 1バーずつ | `add_data` → `run(streaming=True)` → `clear_data` サイクル | ✅ **採用** |
| C: event-driven callback | 全データ登録後 `run()` 1回、Strategy でコールバック | ✅ （将来候補） |

**採用方式: B（streaming 1バーずつ）**

```
step() ごとに:
  1. _current_data を現在バーまで更新
  2. strategy_fn(self) を呼ぶ（現在バーが見える状態）
  3. engine.add_data([bar])
  4. engine.run(streaming=True)  ← 最終バーのみ streaming=False
     └─ on_bar() が発火 → 注文キューをフラッシュ
  5. engine.clear_data()
  6. self._step_index += 1
```

> [!IMPORTANT]
> NautilusTraderには**ステップ実行API（[step()](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/game_setup.py#102-115)）が存在しません**。
> 本計画では**streaming モードで1バーずつデータを追加して `run()` を呼ぶことでステップ実行をエミュレート**するアダプター層を作成します。

> [!WARNING]
> NautilusTraderはRust/Cythonベースの高性能エンジンで、**Pyodide（WASM）環境では動作しません**。
> [pyodide.py](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/pyodide.py) と [wasm-intro.py](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/wasm-intro.py) は BackcastPro のままにするか、別途対応が必要です。

---

## Proposed Changes

### NautilusTrader アダプター層（新規作成）

NautilusTraderの`BacktestEngine`をラップし、既存のゲームインターフェースと同じAPI（[step()](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/game_setup.py#102-115), [buy()](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/game_setup.py#83-90), [sell()](file:///C:/Users/sasai/Documents/BackcastPro/src/BackcastPro/backtest.py#406-439), [equity](file:///C:/Users/sasai/Documents/BackcastPro/src/BackcastPro/backtest.py#477-483), [trades](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/game_setup.py#133-144)等）を提供する。

#### [NEW] [nautilus_adapter.py](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/nautilus_adapter.py)

NautilusTrader ↔ ゲームUIのブリッジ。以下のクラスを含む：

---

#### `NautilusBacktest` クラス — BackcastPro.Backtest との完全API互換表

| BackcastPro メソッド/プロパティ | NautilusBacktest での実装方法 |
|---|---|
| `__init__(data, cash, commission, ...)` | BacktestEngine 初期化、Venue・Instrument 設定（下記パラメータ表参照） |
| `set_data(dct)` | OHLCV DataFrame → Bar リストに変換、`_all_bars_by_ts` として保持。完了後 `start()` を自動呼び出し（BackcastPro互換） |
| `set_cash(cash)` | `_initial_cash` を更新、次の `start()` で反映 |
| `set_strategy(fn)` | `_strategy_fn` に格納（`step()` 内で `_current_data` 更新後に呼び出す） |
| `start()` | エンジン初期化、`_step_index = 0`、`_is_finished = False` |
| `reset()` | `engine.reset()` → `_step_index = 0`、`_is_finished = False` |
| `step() → bool` | streaming 1バーサイクル実行（詳細下記） |
| `goto(step, strategy)` | `step < _step_index` なら `reset()` してから `step()` を繰り返す |
| `run() → pd.Series` | 全バー `step()` → `finalize()` |
| `finalize() → pd.Series` | `engine.get_result()` から統計を生成 |
| `buy(code, size, limit, stop, sl, tp, tag)` | 注文キューに追加、次の `on_bar()` で `submit_order()` |
| `sell(code, size, limit, stop, sl, tp, tag)` | 売り注文キューに追加、次の `on_bar()` で `submit_order()` |
| `equity` (property) | `cash + Σ(open_pos.signed_qty × current_close)` |
| `cash` (property) | `account.balance_free(JPY).as_decimal()` |
| `trades` (property) | open positions → `TradeCompat` リスト |
| `closed_trades` (property) | closed positions → `TradeCompat` リスト |
| `orders` (property) | open orders → `OrderCompat` リスト |
| `position` (property) | `Position._empty()` 互換オブジェクト（後方互換） |
| `position_of(code)` | `cache.positions_open()` から銘柄別に集計 |
| `data` (property) | `_current_data`（現在ステップまでのスライス済み DataFrame） |
| `current_time` (property) | `_all_timestamps[_step_index - 1]` |
| `progress` (property) | `_step_index / len(_all_timestamps)` |
| `step_index` (property) | `_step_index`（read-only） |
| `is_finished` (property) | `_is_finished` |
| `get_state_snapshot()` | 辞書形式でスナップショットを返す |
| `add_trade_callback(cb)` | `_trade_callbacks` リストに追加 |
| `_chart_state` | `Backtest_Wrapper` が設定する属性。`NautilusBacktest` は `__dict__` で動的に受け付ける |

**`__init__` パラメータの実装方針（Phase 1）**:

| パラメータ | Phase 1 の扱い |
|---|---|
| `cash` | Venue の初期残高として設定 |
| `commission` | `FeeModel` として設定（float のみ対応、callable は Phase 2 以降） |
| `spread` | `0.0` 固定（Phase 1 では未実装） |
| `margin` | `1.0` 固定（レバレッジなし、Phase 1 では未実装） |
| `trade_on_close` | `False` 固定（次バー始値約定、Phase 1 では未実装） |
| `exclusive_orders` | `False` 固定（Phase 1 では未実装） |
| `finalize_trades` | `True` 固定（Phase 1 では全オープン取引を終値でクローズ） |

> [!NOTE]
> `spread`, `margin`, `trade_on_close`, `exclusive_orders` は現在のゲームUIでは使用されていないため、Phase 1 では固定値でスタブする。

**`step()` の詳細フロー**:
```python
def step(self) -> bool:
    if self._is_finished:
        return False
    # 1. _current_data を現在バーまで更新（戦略が現在バーを見える状態にする）
    self._update_current_data()  # _bars_flat[_step_index] の値を _current_data に反映
    # 2. 戦略関数を呼ぶ（BackcastPro 互換: 現在バーのデータで判断）
    if self._strategy_fn:
        self._strategy_fn(self)
    # 3. streaming サイクル（注文キューは on_bar() でフラッシュ）
    bar = self._bars_flat[self._step_index]
    self._engine.add_data([bar])
    is_last = (self._step_index == len(self._bars_flat) - 1)
    self._engine.run(streaming=not is_last)
    self._engine.clear_data()
    self._step_index += 1
    if is_last:
        self._is_finished = True
    return not self._is_finished
```

> [!CAUTION]
> **`_update_current_data()` は必ず戦略呼び出しの前に行うこと。**
> BackcastPro の `step()` は「現在バーのスライス更新 → 戦略呼び出し → ブローカー処理」の順。
> NautilusBacktest でこの順序を逆にすると、戦略が1ステップ古いデータで判断することになり、
> SMA等のインジケーターが1バーずれる。

---

#### `InteractiveStrategy` クラス — NautilusTrader の `Strategy` を継承

- `on_bar()` でユーザーからの注文キューをフラッシュ（`submit_order()` を呼び出すのみ）
- `on_order_filled()` で `_trade_callbacks` を呼び出し
- 戦略ロジック自体は `NautilusBacktest.step()` が呼ぶ `_strategy_fn` に委譲するため、`on_bar()` の責務は「注文のフラッシュ」のみ

#### `TradeCompat` クラス — Trade オブジェクト互換層

BackcastPro の `Trade` と同じプロパティ/メソッドを提供する:

| BackcastPro `Trade` | `TradeCompat` の実装 |
|---|---|
| `trade.code` | `position.instrument_id.symbol.value` |
| `trade.size` | `int(position.signed_qty)` |
| `trade.entry_price` | `float(position.avg_px_open)` |
| `trade.pl` | `float(position.unrealized_pnl(...).as_decimal())` |
| `trade.close()` | 売り注文キューに追加して次の `on_bar()` で約定 |

#### その他ヘルパー・例外クラス

- **`create_jpx_equity(code, venue)`**: 日本株のEquityインストゥルメントを生成
- **`ohlcv_to_bars(df, instrument)`**: BackcastProのDataFrame → NautilusTrader の Bar リストに変換
- **`BankruptError`**: 互換性用（equity <= 0 検知時に raise）

---

### 既存ファイル修正

#### [BUGFIX] [bridge.py](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/bridge.py) — Phase 0 で先行修正（NautilusTrader移行と独立）

bridge.py には NautilusTrader 移行とは無関係の既存バグが3つある。Phase 0 として先に修正する。

**バグ1**: `Backtest` を直接使っているが `color_theme` 引数が存在しない（`TypeError`）
```diff
-from BackcastPro import Backtest, get_stock_daily
+from backtest_wrapper import Backtest_Wrapper as Backtest
+from BackcastPro import get_stock_daily
```
```diff
-bt = Backtest(
-    cash=100_000,
-    commission=0.001,
-    finalize_trades=True,
-    color_theme="light",
-)
+bt = Backtest(
+    cash=100_000,
+    commission=0.001,
+    finalize_trades=True,
+    color_theme="light",
+)
```
（`Backtest_Wrapper` に変更することで `color_theme` と `_chart_state` が正しく扱われる）

**バグ2**: `bt._chart_state.reset()` が `AttributeError`（`Backtest` には `_chart_state` がない）
→ バグ1の修正（`Backtest_Wrapper` 使用）で自動的に解消。

**バグ3**: `bt.trades()` を callable として呼んでいるが `@property`
```diff
-    for trade in bt.trades():
+    for trade in bt.trades:
```

#### [MODIFY] [backtest_wrapper.py](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/backtest_wrapper.py) — Phase 2

```diff
-from BackcastPro import Backtest, get_stock_daily as _get_stock_daily
+from nautilus_adapter import NautilusBacktest as Backtest
```

`Backtest_Wrapper` は `NautilusBacktest` を継承する形に変更。`_ChartState` はそのまま維持。
`_chart_state` は動的属性として `NautilusBacktest` 側で透過的に扱われる。

#### [MODIFY] [game_setup.py](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/game_setup.py) — Phase 2

```diff
-from BackcastPro import get_stock_daily as _get_stock_daily, BankruptError
+from BackcastPro import get_stock_daily as _get_stock_daily
+from nautilus_adapter import BankruptError
```

データ取得（`_get_stock_daily`）はBackcastProを維持。`BankruptError` は新アダプターから。

#### [MODIFY] [bridge.py](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/bridge.py) — Phase 2

```diff
-from backtest_wrapper import Backtest_Wrapper as Backtest
+from backtest_wrapper import Backtest_Wrapper as Backtest  # 変更なし（Phase 0 で修正済み）
```

Phase 0 で `Backtest_Wrapper` 使用に切り替え済みのため、Phase 2 では `backtest_wrapper.py` の差し替えのみで自動的に NautilusBacktest に切り替わる。

#### [MODIFY] [full_mode.py](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/full_mode.py) — Phase 2

同様に[Backtest](file:///C:/Users/sasai/Documents/BackcastPro/src/BackcastPro/backtest.py#19-644)のインポート元を変更。[get_stock_daily](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/game_setup.py#161-170)はBackcastProのまま。

#### [MODIFY] [sandbox.py](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/sandbox.py) — Phase 2

同様にインポート変更。

#### [MODIFY] [headless_broadcast.py](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/headless_broadcast.py) — Phase 2

[Backtest](file:///C:/Users/sasai/Documents/BackcastPro/src/BackcastPro/backtest.py#19-644) 型アノテーションのインポート元を変更。

#### [NO CHANGE] [chart.py](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/chart.py)

`BackcastPro.api.stocks_price` のインポートはデータ取得用なので変更なし。

#### [NO CHANGE] [board.py](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/board.py)

`BackcastPro.api.stocks_board` のインポートはデータ取得用なので変更なし。

#### [NO CHANGE] [pyodide.py](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/pyodide.py)

Pyodide環境ではNautilusTraderは動作しないため変更なし。

#### [MODIFY] [backcast.py](file:///C:/Users/sasai/AppData/Roaming/marimo/notebooks/backcast.py)

ノートブック自体の変更は不要（`game_setup` 経由でラップされるため）。ただし説明テキストを更新。

---

### 依存関係

#### nautilus_trader インストール

BackcastPro プロジェクトの仮想環境に `nautilus_trader` を追加インストール。

```
uv pip install nautilus_trader
```

**確認済み**: v1.221.0 が `.venv`（Python 3.11.14）に既にインストール済み。

---

## 実装フェーズ

### ✅ Phase 0: bridge.py 既存バグ修正（完了）

以下の3つのバグを修正済み（NautilusTrader移行と独立した修正）：

1. ✅ `bridge.py` のインポートを `Backtest_Wrapper` に変更（`color_theme` + `_chart_state` のバグ解消）
2. ✅ `bridge.py` の `bt.trades()` → `bt.trades`（property 呼び出しのバグ修正）

### ✅ Phase 1: `nautilus_adapter.py` 単体実装・ユニットテスト（完了）

1. ✅ `nautilus_adapter.py` を新規作成（328行）
   - `NautilusBacktest`, `TradeCompat`, `_InteractiveStrategy`, `BankruptError`, `create_jpx_equity()`, `ohlcv_to_bars()`
2. ✅ `tests/test_nautilus_adapter.py` を新規作成（38テスト）
3. ✅ 全38テスト通過（`pytest tests/test_nautilus_adapter.py` で 2.74秒）

**実際に実装したファイル**:
- [`nautilus_adapter.py`](file:///C:/Users/sasai/Documents/marimo/src-tauri/resources/files/nautilus_adapter.py) — NautilusTrader アダプター本体
- [`tests/test_nautilus_adapter.py`](file:///C:/Users/sasai/Documents/BackcastPro/tests/test_nautilus_adapter.py) — ユニットテスト

### ✅ Phase 2: 各ファイルのインポート変更（完了）

| ファイル | 変更内容 | 状態 |
|---|---|---|
| `backtest_wrapper.py` | `BackcastPro.Backtest` → `nautilus_adapter.NautilusBacktest` | ✅ |
| `game_setup.py` | `BankruptError` を `nautilus_adapter` から取得 | ✅ |
| `full_mode.py` | `Backtest` を `backtest_wrapper.Backtest_Wrapper` 経由に変更 | ✅ |
| `bridge.py` | Phase 0 で修正済み。追加変更なし | ✅ |
| `sandbox.py` | `game_setup` 経由のため変更不要 | ✅（変更なし） |
| `headless_broadcast.py` | TYPE_CHECKING のみ。実行時影響なし | ✅（変更なし） |

> [!NOTE]
> `backtest_wrapper.py` の変更が核心。`class Backtest_Wrapper(Backtest)` の構造を変えず、
> `Backtest` のインポート元を差し替えるだけで全体が NautilusBacktest に切り替わる。

### ⏳ Phase 3: 統合テスト（ユーザーによる動作確認）

`pnpm tauri:dev` でアプリを起動し、実際のゲームUIを操作して動作確認。

**確認チェックリスト**:
- [ ] `bt.chart("7203")` でチャートが表示される
- [ ] `bt.buy()` で注文が作成される
- [ ] `bt.step()` で日が進み、注文が約定する
- [ ] `bt.sell()` で保有株を売却できる
- [ ] equity / cash が正しく更新される
- [ ] `BankruptError` が equity <= 0 で発生する
- [ ] ブリッジモード（bridge.py）の golden cross 戦略が動作する
- [ ] フルモード（full_mode.py）が動作する

### ✅ blacksheep.py — run 方式への移行（コード変更完了、動作未確認）

`C:\Users\sasai\AppData\Roaming\marimo\notebooks\blacksheep.py` を NautilusTrader チュートリアルの run 方式に書き換え済み。

変更内容:
- ✅ `for i in range(200): bt.step()` ループを `bt.run(strategy=..., step_callback=...)` に置き換え
- ✅ 戦略ロジックを `strategy()` 関数として分離
- ✅ `update_all_backtest_charts` を `step_callback` として渡し（チャート更新タイミング維持）

⚠️ **未解決**: `nautilus_adapter.py` の `run(strategy, step_callback)` 変更が marimo ノートブックに反映されていない（知見10参照）。
正しい `nautilus_adapter.py` のパスを特定し、そちらを編集する必要がある。

### フォールバック戦略

NautilusTrader移行が困難な場合（特定APIの再現が不可能と判明した場合）は、
BackcastPro を継続利用し、移行を中止する。
Phase 1 のユニットテストが通らない場合はこのフォールバックを適用する。

---

## Verification Plan

### ✅ Phase 0: 既存バグ修正の確認（完了）

`tests/test_nautilus_adapter.py::TestPhase0Compat` で検証済み：

```python
def test_bridge_trades_is_property():
    """bt.trades が property であり callable でないこと"""
    bt = Backtest_Wrapper(cash=100_000)
    assert not callable(bt.trades)

def test_bridge_chart_state_exists():
    """Backtest_Wrapper に _chart_state が存在すること"""
    bt = Backtest_Wrapper(cash=100_000, color_theme="light")
    assert hasattr(bt, "_chart_state")
    bt._chart_state.reset()  # AttributeError が出ないこと
```

### ✅ Phase 1: ユニットテスト（完了 — 38/38 通過）

実行コマンド:
```bash
cd C:/Users/sasai/Documents/BackcastPro
.venv/Scripts/python -m pytest tests/test_nautilus_adapter.py -v
# 38 passed in 2.74s
```

`tests/test_nautilus_adapter.py` に実装済み:

```python
def test_step_execution():
    bt = NautilusBacktest(data={"7203": synthetic_df})
    assert bt.is_finished == False
    assert bt.step_index == 0
    bt.step()
    assert bt.step_index == 1
    assert bt.current_time is not None

def test_current_data_visible_to_strategy():
    """step() 内で戦略が呼ばれる時点で現在バーが bt.data に見えること"""
    seen_lengths = []
    def strategy(bt):
        seen_lengths.append(len(bt.data["7203"]))
    bt = NautilusBacktest(data={"7203": synthetic_df})
    bt.set_strategy(strategy)
    bt.step()  # step 1: 戦略が呼ばれる時点で data に1行目が見えること
    bt.step()  # step 2: 戦略が呼ばれる時点で data に2行目が見えること
    assert seen_lengths == [1, 2], f"expected [1, 2], got {seen_lengths}"

def test_set_data_auto_starts():
    """set_data() の後に明示的 start() なしで step() が動作すること"""
    bt = NautilusBacktest(cash=100_000)
    bt.set_data({"7203": synthetic_df})  # start() が自動で呼ばれる
    assert bt.step()  # RuntimeError が出ないこと

def test_buy_and_equity():
    bt = NautilusBacktest(data={"7203": synthetic_df})
    bt.step()  # 最初のバーを進める
    initial_equity = bt.equity
    bt.buy()
    bt.step()  # 注文約定
    assert bt.equity != initial_equity  # ポジションのMTM反映

def test_goto():
    bt = NautilusBacktest(data={"7203": synthetic_df})
    bt.goto(5)
    assert bt.step_index == 5

def test_finalize():
    bt = NautilusBacktest(data={"7203": synthetic_df})
    while not bt.is_finished:
        bt.step()
    result = bt.finalize()
    assert isinstance(result, pd.Series)

def test_all_api_methods():
    """全メソッド/プロパティが例外なく呼び出せること"""
    bt = NautilusBacktest(data={"7203": synthetic_df})
    bt.set_cash(500_000)
    bt.set_strategy(lambda b: None)
    bt.start()
    bt.step()
    _ = bt.equity
    _ = bt.cash
    _ = bt.trades
    _ = bt.closed_trades
    _ = bt.orders
    _ = bt.position
    _ = bt.position_of("7203")
    _ = bt.data
    _ = bt.current_time
    _ = bt.progress
    _ = bt.step_index
    _ = bt.is_finished
    _ = bt.get_state_snapshot()
    bt.add_trade_callback(lambda e, t: None)
    bt.reset()
    bt.goto(3)
    bt.finalize()
```

### ⏳ Phase 3: 手動確認（ユーザーによるテスト）

1. **nautilus_trader インストール確認**
   - ✅ `python -c "import nautilus_trader; print(nautilus_trader.__version__)"` → `1.221.0` 確認済み

2. **ゲームUI動作確認**（ユーザーによるテスト）
   ```bash
   pnpm tauri:dev
   ```
   - [ ] [backcast.py](file:///C:/Users/sasai/AppData/Roaming/marimo/notebooks/backcast.py) ノートブックを開く
   - [ ] `bt.chart("7203")` でチャートが表示される
   - [ ] `bt.buy()` で注文が作成される
   - [ ] `bt.step()` で日が進み、注文が約定する
   - [ ] `bt.sell()` で保有株を売却できる
   - [ ] equity / cash が正しく更新される

3. **エラーハンドリング確認**
   - [ ] equity <= 0 になった場合に `BankruptError` が発生すること

4. **回帰テスト**
   ```bash
   cd C:/Users/sasai/Documents/BackcastPro
   .venv/Scripts/python -m pytest tests/test_nautilus_adapter.py -v
   ```
