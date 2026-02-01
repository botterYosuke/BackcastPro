# 修正計画: 相対サイズの解釈変更（案C）

## 問題の概要

`bt.sell()` または `bt.buy()` で `size` を省略（相対サイズ=0.9999）した場合、反対ポジションを保有していてもクローズされず、マージン不足でキャンセルされる。

## 修正方針: 案C

相対サイズ（-1 < size < 1）の解釈を根本的に変更する。

| 従来の解釈 | 新しい解釈（案C） |
|-----------|------------------|
| 「利用可能マージンの99.99%」 | 「全ポジションクローズまたは全力買い/売り」 |

### 新しいロジック

```
bt.sell(size省略) の場合:
  1. 同一銘柄のロングポジションあり？
     → Yes: 全ロングをクローズ
     → No:  全資産で新規空売り

bt.buy(size省略) の場合:
  1. 同一銘柄のショートポジションあり？
     → Yes: 全ショートをクローズ
     → No:  全資産で新規買い
```

## 期待動作

| 条件 | 動作 |
|------|------|
| `sell(size省略)` & ロング保有 | 全ロングクローズ |
| `sell(size省略)` & 保有なし | 全資産で新規ショート |
| `sell(size省略)` & ショート保有 | `margin_available`で売り増し |
| `buy(size省略)` & ショート保有 | 全ショートクローズ |
| `buy(size省略)` & 保有なし | 全資産で新規ロング |
| `buy(size省略)` & ロング保有 | `margin_available`で買い増し |
| `sell(size=50)` & 100株ロング | 50株クローズ |
| `sell(size=200)` & 100株ロング | 100株クローズ + 100株新規ショート |
| `buy(size=200)` & 100株ロング | 200株追加（合計300株） |
| `sell(size=200)` & 100株ショート | 200株追加（合計-300株） |


## 修正箇所

### ファイル: `src/BackcastPro/_broker.py`

### 修正1: 相対サイズ処理の変更

[_broker.py:307-346](_broker.py#L307-L346) を以下のように変更:

```python
# 注文サイズが比例的に指定された場合の処理
size = order.size
if -1 < size < 1:
    # 同一銘柄の反対ポジションを取得
    opposite_position = sum(
        trade.size for trade in self.trades
        if trade.code == order.code and trade.is_long != order.is_long
    )

    # 同一銘柄の同方向ポジションを取得
    same_direction_position = sum(
        trade.size for trade in self.trades
        if trade.code == order.code and trade.is_long == order.is_long
    )

    if opposite_position:
        # 反対ポジションがある → 全クローズ
        size = -opposite_position
    elif same_direction_position:
        # 同方向ポジションがある → margin_availableで買い増し
        size = copysign(
            int((self.margin_available * self._leverage * abs(size))
                // adjusted_price_plus_commission),
            size
        )
    else:
        # ポジションがない → 全資産で新規ポジション
        size = copysign(
            int((self.equity * self._leverage * abs(size))
                // adjusted_price_plus_commission),
            size
        )

    if not size:
        warnings.warn(
            f'{self._current_time}: ブローカーは相対サイズの注文を'
            f'不十分な資産のためキャンセルしました。', category=UserWarning)
        self.orders.remove(order)
        continue

assert size == round(size)
need_size = int(size)
```

### 修正2: 既存のFIFOクローズ処理に銘柄フィルタ追加（重大バグ修正）

[_broker.py:331-333](_broker.py#L331-L333) の既存コードに銘柄チェックが欠如:

```python
# 現在のコード（バグ）
for trade in list(self.trades):
    if trade.is_long == order.is_long:
        continue  # ← trade.code のチェックがない！
```

**修正後:**

```python
for trade in list(self.trades):
    if trade.is_long == order.is_long or trade.code != order.code:
        continue  # 同方向 または 異なる銘柄 はスキップ
```

> ⚠️ **マルチシンボル環境で異なる銘柄のポジションを誤ってクローズするリスクを防止**

---

## 部分的な相対サイズの扱い

| 指定 | 反対ポジションあり | 同方向ポジションあり | ポジションなし |
|------|-------------------|---------------------|---------------|
| `size省略` (0.9999) | 全クローズ | margin_availableで買い増し | 全力新規 |
| `size=0.5` | **全クローズ** | margin_availableの50%で買い増し | 資産の50%で新規 |
| `size=0.3` | **全クローズ** | margin_availableの30%で買い増し | 資産の30%で新規 |

**設計判断**: 反対ポジションがある場合、相対サイズの割合に関わらず**全クローズ**を優先する。

理由:
- 「売り注文を出す」という意図は「ロングを手放したい」と解釈
- 部分クローズが必要な場合は絶対サイズ（`size=50`）を使用すべき

---

## 同方向ポジション追加時の動作

相対サイズで同方向のポジションを追加しようとした場合の動作:

### 例: 300株ロング保有中（30%使用）に `bt.buy()` 実行

```
1. opposite_position = 0（反対ポジションなし）
2. same_direction_position = 300（同方向ポジションあり）
3. size = margin_available * leverage / price で計算

   margin_available = equity - margin_used
                    = 100万円 - 30万円（既存300株分）
                    = 70万円

   size = 70万円 * 0.9999 / 1000円 ≒ 699株

4. FIFOクローズ処理: 反対ポジションなし → スキップ
5. need_size = 699（そのまま）

6. 結果: 300株 + 699株 = 999株のロングポジション
```

### 設計判断

| 動作 | 理由 |
|------|------|
| **margin_availableで買い増し** | 余剰資金を活用して同方向ポジションを追加 |

**注意事項:**
- `margin_available`が0の場合（全力買い済み）はワーニングが出て注文キャンセル
- 部分的な相対サイズ（`size=0.5`）は`margin_available`の50%で買い増し

### 動作まとめ

| シナリオ | 相対サイズ指定時の動作 |
|----------|----------------------|
| 反対ポジションあり | 全クローズ ✅ |
| ポジションなし | 全力買い/売り ✅ |
| 同方向ポジションあり | `margin_available`で買い増し ✅ |

---

## 案Aとの違い

| 状況 | 案A | 案C |
|------|-----|-----|
| 反対ポジションあり | 全クローズ | 全クローズ |
| 反対ポジションなし | `margin_available` の99.99% | `equity` の99.99%（全力） |

### 具体例

**前提**: 100万円で1000株保有中、`bt.sell()` を実行

| 案 | 計算基準 | 結果 |
|----|----------|------|
| 案A | `margin_available ≒ 0` | 0株 → キャンセル |
| 案C | 反対ポジション1000株 | 1000株クローズ |

**前提**: 100万円でポジションなし、`bt.buy()` を実行

| 案 | 計算基準 | 結果 |
|----|----------|------|
| 案A | `margin_available = 100万` | 約1000株購入 |
| 案C | `equity = 100万` | 約1000株購入（同じ） |

## 検証方法

### ユニットテスト

```python
# tests/test_relative_size_option_c.py

def test_sell_closes_long_position():
    """相対サイズのsellでロングポジションが全クローズされる"""
    bt = Backtest(cash=1_000_000)
    bt.set_data({"7203": toyota_data})
    bt.start()

    bt.buy(code="7203")
    bt.step()
    initial_position = bt.position_of("7203")
    assert initial_position > 0

    bt.sell(code="7203")  # size省略
    bt.step()
    assert bt.position_of("7203") == 0  # 全クローズ


def test_buy_closes_short_position():
    """相対サイズのbuyでショートポジションが全クローズされる"""
    bt = Backtest(cash=1_000_000)
    bt.set_data({"7203": toyota_data})
    bt.start()

    bt.sell(code="7203")
    bt.step()
    initial_position = bt.position_of("7203")
    assert initial_position < 0

    bt.buy(code="7203")  # size省略
    bt.step()
    assert bt.position_of("7203") == 0  # 全クローズ


def test_sell_full_short_when_no_position():
    """ポジションなしで相対サイズsellは全力空売り"""
    bt = Backtest(cash=1_000_000)
    bt.set_data({"7203": toyota_data})
    bt.start()

    assert bt.position_of("7203") == 0

    bt.sell(code="7203")  # size省略
    bt.step()
    assert bt.position_of("7203") < 0  # 空売りポジション


def test_buy_full_long_when_no_position():
    """ポジションなしで相対サイズbuyは全力買い"""
    bt = Backtest(cash=1_000_000)
    bt.set_data({"7203": toyota_data})
    bt.start()

    assert bt.position_of("7203") == 0

    bt.buy(code="7203")  # size省略
    bt.step()
    assert bt.position_of("7203") > 0  # ロングポジション


def test_partial_relative_size_still_closes_all():
    """size=0.5 でも反対ポジションがあれば全クローズ"""
    bt = Backtest(cash=1_000_000)
    bt.set_data({"7203": toyota_data})
    bt.start()

    bt.buy(code="7203")
    bt.step()
    initial_position = bt.position_of("7203")
    assert initial_position > 0

    bt.sell(code="7203", size=0.5)  # 部分的な相対サイズ（sell内部で-0.5に変換）
    bt.step()
    assert bt.position_of("7203") == 0  # それでも全クローズ


def test_multi_symbol_isolation():
    """異なる銘柄のポジションに影響しないことを確認"""
    bt = Backtest(cash=1_000_000)
    bt.set_data({"7203": toyota_data, "6758": sony_data})
    bt.start()

    # 両方の銘柄でポジション取得
    bt.buy(code="7203")
    bt.buy(code="6758")
    bt.step()
    assert bt.position_of("7203") > 0
    assert bt.position_of("6758") > 0

    # 7203のみ売却
    bt.sell(code="7203")
    bt.step()
    assert bt.position_of("7203") == 0  # クローズ
    assert bt.position_of("6758") > 0   # 影響なし


def test_multi_symbol_fifo_isolation():
    """FIFOクローズ処理が他銘柄に影響しないことを確認"""
    bt = Backtest(cash=1_000_000)
    bt.set_data({"7203": toyota_data, "6758": sony_data})
    bt.start()

    bt.buy(code="7203", size=100)
    bt.buy(code="6758", size=100)
    bt.step()

    # 7203を200株売り（100クローズ + 100新規ショート）
    bt.sell(code="7203", size=200)
    bt.step()
    assert bt.position_of("7203") == -100  # ショートポジション
    assert bt.position_of("6758") == 100   # 影響なし


def test_same_direction_relative_size_cancelled():
    """同方向ポジション保有中に相対サイズ買いはマージン不足でキャンセル"""
    bt = Backtest(cash=1_000_000)
    bt.set_data({"7203": toyota_data})
    bt.start()

    # まず全力買い
    bt.buy(code="7203")
    bt.step()
    initial_position = bt.position_of("7203")
    assert initial_position > 0

    # 同方向に相対サイズで追加買い → マージン不足でキャンセル
    with pytest.warns(UserWarning, match="不十分な資産"):
        bt.buy(code="7203")  # size省略 = 相対サイズ
        bt.step()

    # ポジションは変わらない（注文がキャンセルされたため）
    assert bt.position_of("7203") == initial_position
```

### 手動テスト

`backcast.py` サンプルで以下を確認:
1. BUY後にSELLでポジションがクローズされる
2. デッドクロス時に `pos=0` になる
3. 複数回のBUY/SELLサイクルが正常動作

### backcast.py の簡略化確認

修正後、現在のワークアラウンド:

```python
# 現在（L122-124）
for trade in bt.trades:
    if trade.code == code:
        trade.close()
```

が以下に簡略化できることを確認:

```python
# 修正後
bt.sell(code=code)
```

## 実装ステップ

1. [ ] `_broker.py` L310-326 を修正（相対サイズ処理）
2. [ ] `_broker.py` L332 を修正（銘柄フィルタ追加）
3. [ ] ユニットテストを作成・実行
4. [ ] `backcast.py` で手動検証
5. [ ] `backcast.py` のワークアラウンドを簡略化して動作確認
6. [ ] 既存テストの回帰確認

## 影響範囲

| 箇所 | 変更内容 |
|------|----------|
| L310-326 | 相対サイズ処理を `equity` ベースに変更 |
| L332 | 銘柄フィルタ追加（バグ修正） |

- **破壊的変更**: 従来「余りマージンの99.99%」だった動作が「全力」に変わる
- **ヘッジングモード廃止**: `hedging` パラメータを削除し、常にFIFO方式で動作
- マルチシンボル環境での動作が正しくなる（L332修正）
- 同方向ポジション追加時は `margin_available` で買い増し可能に

## リスクと対策

| リスク | 対策 |
|--------|------|
| 既存コードの動作変更 | 十分なテストカバレッジ |
| 意図しない全力買い | ドキュメント更新で明記 |
| L332修正の副作用 | マルチシンボルテストで検証 |
| hedging=True使用コード | 破壊的変更として明記 |

## 修正範囲サマリ

| ファイル | 変更内容 | 重要度 |
|----------|----------|--------|
| `_broker.py` L307-346 | 相対サイズ処理を変更（同方向買い増し追加） | 主目的 |
| `_broker.py` L351-370 | FIFO処理の銘柄フィルタ追加 | バグ修正 |
| `_broker.py` | `hedging` パラメータと `_hedging` 属性を削除 | 簡略化 |
| `backtest.py` | `hedging` パラメータを削除 | 簡略化 |
