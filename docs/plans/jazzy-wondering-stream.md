# BackcastProからmarimo依存を除去する計画

## 進捗状況

| Phase | 状態 | 説明 |
|-------|------|------|
| Phase 1 | ✅ 完了 | BackcastProにパブリックAPI追加 |
| Phase 2 | ✅ 完了 | ヘッドレス関数をノートブックに移動 |
| Phase 3 | ✅ 完了 | ノートブックの呼び出しを更新 |
| Phase 4 | ✅ 完了 | BackcastProから関数を削除 |
| 追加修正 | ✅ 完了 | コールバック重複登録の防止 |

## 概要

`publish_state_headless`と`publish_trade_event_headless`関数をBackcastProからmarimoノートブックの`app.setup`に移動し、BackcastProからmarimo依存を完全に除去する。

---

## 新たな知見

### 1. コールバック機構の競合問題
既存の`start()`メソッドには2つの独立したコールバック機構が存在していた：
- `_trade_event_publisher`（AnyWidget用）
- `_headless_trade_events_enabled`（ヘッドレス用）

**発見**: `set_on_trade_event()`は単一コールバックのみ対応。後から設定すると上書きされる。

**解決**: 複数コールバック対応の`add_trade_callback()`APIを導入し、内部で`emit_all()`関数で全コールバックを呼び出す。

### 2. コールバック重複登録の問題
**発見**: `do_step()`内で`enable_headless_trade_events(bt)`を呼ぶと、ループ再開時（run→stop→run）に同じコールバックが重複登録される。

**解決**: コールバック登録を`bt`初期化直後に移動し、1回だけ呼ぶようにした。

### 3. privateアクセスの問題
**発見**: ノートブックが`bt._step_index`（private属性）を直接参照していた。

**解決**: `step_index`パブリックプロパティを追加。

---

## 設計変更

### 当初計画からの変更点

| 項目 | 当初計画 | 最終実装 |
|------|---------|---------|
| コールバックAPI | `set_trade_callback()` | `add_trade_callback()` |
| コールバック管理 | 単一コールバック | 複数コールバックリスト |
| 状態取得 | 各プロパティ個別アクセス | `get_state_snapshot()`純粋関数 |
| 登録タイミング | `do_step()`内 | `bt`初期化直後 |

### アーキテクチャ図

```
┌─────────────────────────────────────────────────────────────┐
│ marimo notebook (backcast.py)                               │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ app.setup                                               │ │
│ │  ├─ publish_state_headless(bt, ...)  ← marimo依存      │ │
│ │  ├─ publish_trade_event_headless(...) ← marimo依存     │ │
│ │  ├─ enable_headless_trade_events(bt) ← marimo依存      │ │
│ │  │                                                      │ │
│ │  └─ bt = Backtest(...)                                  │ │
│ │       └─ enable_headless_trade_events(bt)  ← 1回だけ   │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ bt.add_trade_callback(on_trade)
                           │ bt.get_state_snapshot()
                           │ bt.step_index
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ BackcastPro (backtest.py) - marimo非依存                    │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Backtest                                                │ │
│ │  ├─ step_index: int (property)                          │ │
│ │  ├─ get_state_snapshot() -> dict                        │ │
│ │  ├─ add_trade_callback(callback)                        │ │
│ │  └─ _trade_callbacks: list[Callback]                    │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Tips

### 1. 純粋関数パターン
フレームワーク依存のコードを分離する際は、**純粋関数**（副作用なし、外部依存なし）をライブラリ側に残し、フレームワーク固有の出力処理だけを呼び出し側に移動する。

```python
# ライブラリ側（純粋関数）
def get_state_snapshot(self) -> dict:
    return {"equity": self.equity, ...}

# フレームワーク側（marimo依存）
def publish_state(bt):
    state = bt.get_state_snapshot()  # 純粋関数を使用
    mo.output.replace(Html(...))     # marimo固有の出力
```

### 2. コールバックリストパターン
単一コールバックAPIを複数対応に拡張する際は、リストで管理し`emit_all`で全呼び出しする。

```python
self._callbacks = []

def add_callback(self, cb):
    self._callbacks.append(cb)

def _emit_all(self, *args):
    for cb in self._callbacks:
        cb(*args)
```

### 3. 重複登録の防止
コールバック登録は**初期化時に1回だけ**行う。ループ内やイベントハンドラ内で登録すると重複する。

```python
# ❌ Bad: ループ開始ごとに重複登録
def do_step():
    enable_headless_trade_events(bt)  # 毎回追加される
    while ...:

# ✅ Good: 初期化時に1回だけ
bt = Backtest(...)
enable_headless_trade_events(bt)  # 1回だけ

def do_step():
    while ...:
```

### 4. フラグによる重複チェック
関数オブジェクトの同一性比較はクロージャでは機能しない。フラグで管理する。

```python
# start()メソッド内
if not getattr(self, "_publisher_registered", False):
    self._trade_callbacks.append(on_trade_publish)
    self._publisher_registered = True
```

---

## 変更ファイル一覧

| ファイル | 変更内容 | 状態 |
|---------|---------|------|
| `BackcastPro/src/BackcastPro/backtest.py` | ヘッドレスメソッド4つ削除、`step_index`/`get_state_snapshot()`追加、コールバック機構統一 | ✅ |
| `C:\Users\sasai\AppData\Roaming\marimo\notebooks\backcast.py` | 3つのスタンドアロン関数追加、呼び出し修正、重複登録防止 | ✅ |
| `C:\Users\sasai\AppData\Roaming\marimo\notebooks\backcast_1.py` | 同様に呼び出し修正、重複登録防止 | ✅ |

---

## 検証方法

1. ✅ **単体テスト**: BackcastProの既存テストが通ること
2. **動作確認**:
   - `marimo edit backcast.py` でローカルサーバー起動
   - バックテスト実行してBroadcastChannelで状態が送信されること確認
   - 取引イベントが正しく発行されること確認
3. ✅ **marimo依存確認**: BackcastProのインポートで`marimo`が不要になったこと確認
4. **コールバック競合テスト**: `_trade_event_publisher`と`add_trade_callback`を同時に使用して両方動作すること確認

---

## 実装詳細（参考）

### Phase 1: BackcastProにパブリックAPIを追加 ✅

**1.1 `step_index`プロパティを公開** ✅
```python
@property
def step_index(self) -> int:
    """現在のステップインデックス（read-only）"""
    return self._step_index
```

**1.2 `get_state_snapshot()`メソッドを追加** ✅
```python
def get_state_snapshot(self) -> dict:
    """現在の状態を辞書で返す（marimo非依存）"""
    positions = {}
    for trade in self.trades:
        positions[trade.code] = positions.get(trade.code, 0) + trade.size
    return {
        "current_time": str(self.current_time) if self.current_time else "-",
        "progress": float(self.progress),
        "equity": float(self.equity),
        "cash": float(self.cash),
        "position": self.position,
        "positions": positions,
        "closed_trades": len(self.closed_trades),
        "step_index": self.step_index,
        "total_steps": len(self.index) if hasattr(self, "index") else 0,
    }
```

**1.3 コールバック機構を統一** ✅
```python
# __init__に追加
self._trade_callbacks: list[Callable[[str, 'Trade'], None]] = []

# 新しいメソッド
def add_trade_callback(self, callback):
    self._trade_callbacks.append(callback)
    if self._broker_instance:
        self._setup_trade_callbacks()

def _setup_trade_callbacks(self):
    if not self._trade_callbacks:
        return
    def emit_all(event_type, trade):
        for cb in self._trade_callbacks:
            cb(event_type, trade)
    self._broker_instance.set_on_trade_event(emit_all)
```

### Phase 2-4: ノートブック移動と削除 ✅

ヘッドレス関数3つをノートブックの`app.setup`に移動し、BackcastProから削除完了。

### 追加修正: コールバック重複登録の防止 ✅

`enable_headless_trade_events(bt)`を`do_step()`内から`bt`初期化直後に移動。
