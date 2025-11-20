# BackcastPro 約定ロジック分析レポート

## 概要

本レポートでは、BackcastProプロジェクトにおける売買約定時の価格決定ロジックについて詳しく分析します。**Open**, **High**, **Low**, **Close**のどの値が約定価格として使用されるかを明確にします。

## 約定価格決定の基本ロジック

### 1. 成行注文（Market Order）の約定価格

成行注文は、`_broker.py`の`_process_orders()`メソッド内で以下のロジックで処理されます：

```python
# 成行注文（Market-if-touched / market order）
# 条件付き注文は常に次の始値で
prev_close = df.Close.iloc[-2]
price = prev_close if self._trade_on_close and not order.is_contingent else open
```

#### 約定価格決定ルール：

1. **`trade_on_close=False`の場合（デフォルト）**：
   - 約定価格 = **Open**（始値）
   - 次のバーの始値で約定

2. **`trade_on_close=True`の場合**：
   - 約定価格 = **Close**（前のバーの終値）
   - 現在のバーの終値で約定

3. **条件付き注文（SL/TP注文）の場合**：
   - 常に**Open**（始値）で約定
   - `trade_on_close`の設定に関係なく

### 2. 指値注文（Limit Order）の約定価格

指値注文の約定価格は以下のロジックで決定されます：

```python
if order.limit:
    is_limit_hit = low <= order.limit if order.is_long else high >= order.limit
    if not is_limit_hit or is_limit_hit_before_stop:
        continue

    # stop_priceが設定されている場合、このバー内で満たされた
    price = (min(stop_price or open, order.limit)
            if order.is_long else
            max(stop_price or open, order.limit))
```

#### 約定価格決定ルール：

1. **ロングポジション**：
   - 約定条件：`Low <= limit_price`
   - 約定価格 = `min(始値 or ストップ価格, 指値価格)`

2. **ショートポジション**：
   - 約定条件：`High >= limit_price`
   - 約定価格 = `max(始値 or ストップ価格, 指値価格)`

### 3. ストップ注文（Stop Order）の約定価格

ストップ注文は以下のロジックで処理されます：

```python
# ストップ条件が満たされたかチェック
stop_price = order.stop
if stop_price:
    is_stop_hit = ((high >= stop_price) if order.is_long else (low <= stop_price))
    if not is_stop_hit:
        continue
    
    # ストップ価格に達すると、ストップ注文は成行/指値注文になる
    order._replace(stop_price=None)
```

#### 約定価格決定ルール：

1. **ロングポジション**：
   - 約定条件：`High >= stop_price`
   - ストップ価格に達した後は成行注文として処理

2. **ショートポジション**：
   - 約定条件：`Low <= stop_price`
   - ストップ価格に達した後は成行注文として処理

### 4. ストップロス/テイクプロフィット注文の約定価格

条件付き注文（SL/TP）は以下のように処理されます：

```python
# 条件付き注文は常に次の始値で
prev_close = df.Close.iloc[-2]
price = prev_close if self._trade_on_close and not order.is_contingent else open
```

#### 約定価格決定ルール：

- **常にOpen（始値）で約定**
- `trade_on_close`の設定に関係なく

## スプレッドと手数料の適用

約定価格は、スプレッドと手数料を考慮して調整されます：

```python
def _adjusted_price(self, code: str, size=None, price=None) -> float:
    """
    Long/short `price`, adjusted for spread.
    In long positions, the adjusted price is a fraction higher, and vice versa.
    """
    return (price or self.last_price(code)) * (1 + copysign(self._spread, size))
```

### 調整ロジック：

1. **ロングポジション**：
   - 調整価格 = 約定価格 × (1 + spread)
   - より高い価格で購入（不利）

2. **ショートポジション**：
   - 調整価格 = 約定価格 × (1 - spread)
   - より低い価格で売却（不利）

## 実際の約定価格の決定フロー

### 1. 基本的な約定価格の決定

```python
# 基本的な約定価格
if order.limit:
    # 指値注文の場合
    price = (min(stop_price or open, order.limit) if order.is_long else
             max(stop_price or open, order.limit))
else:
    # 成行注文の場合
    prev_close = df.Close.iloc[-2]
    price = prev_close if self._trade_on_close and not order.is_contingent else open
```

### 2. スプレッド調整

```python
# スプレッド調整
adjusted_price = self._adjusted_price(code=order.code, size=order.size, price=price)
```

### 3. 手数料計算

```python
# 手数料計算
adjusted_price_plus_commission = \
    adjusted_price + self._commission(order.size, price) / abs(order.size)
```

## 約定価格の優先順位

### 1. 指値注文の場合

1. **ストップ価格が設定されている場合**：
   - ロング：`min(始値, 指値価格)`
   - ショート：`max(始値, 指値価格)`

2. **ストップ価格が設定されていない場合**：
   - ロング：`min(始値, 指値価格)`
   - ショート：`max(始値, 指値価格)`

### 2. 成行注文の場合

1. **`trade_on_close=True`かつ条件付き注文でない場合**：
   - 約定価格 = **前のバーの終値（Close）**

2. **その他の場合**：
   - 約定価格 = **現在のバーの始値（Open）**

## 重要な注意点

### 1. データの取得方法

```python
open, high, low = df.Open.iloc[-1], df.High.iloc[-1], df.Low.iloc[-1]
```

- `iloc[-1]`：現在のバー（最新のローソク足）
- `iloc[-2]`：前のバー（1つ前のローソク足）

### 2. 条件付き注文の特別扱い

```python
# 条件付き注文は常に次の始値で
price = prev_close if self._trade_on_close and not order.is_contingent else open
```

条件付き注文（SL/TP）は`trade_on_close`の設定に関係なく、常に**Open**で約定されます。

### 3. ストップ注文の変換

ストップ価格に達すると、ストップ注文は自動的に成行注文に変換されます：

```python
# ストップ価格に達すると、ストップ注文は成行/指値注文になる
order._replace(stop_price=None)
```

## まとめ

BackcastProにおける約定価格の決定は以下のように要約されます：

1. **成行注文**：
   - デフォルト：**Open**（始値）
   - `trade_on_close=True`：**Close**（前のバーの終値）

2. **指値注文**：
   - ロング：`min(始値, 指値価格)`
   - ショート：`max(始値, 指値価格)`

3. **ストップ注文**：
   - 条件達成後は成行注文として処理

4. **条件付き注文（SL/TP）**：
   - 常に**Open**（始値）

5. **スプレッド調整**：
   - ロング：約定価格 × (1 + spread)
   - ショート：約定価格 × (1 - spread)

このロジックにより、リアルな取引環境をシミュレートし、バックテストの精度を向上させています。
