# 実装計画: 同方向ポジション買い増し + ヘッジングモード廃止

## 概要

1. 同方向ポジション追加時の動作を「キャンセル」から「margin_availableで買い増し」に変更する
2. ヘッジングモード（`hedging`パラメータ）を廃止し、常にFIFO方式で動作させる

## 変更後の期待動作

| 条件 | 動作 |
|------|------|
| `buy(size省略)` & ロング保有 | `margin_available`で買い増し |
| `sell(size省略)` & ショート保有 | `margin_available`で売り増し |
| 反対ポジションあり | 全クローズ（既存動作） |
| ポジションなし | `equity`ベースで全力買い/売り（既存動作） |

## 修正対象ファイル

### 1. `src/BackcastPro/_broker.py` (L312-337)

**変更内容**: 同方向ポジションを検出し、`margin_available`ベースでサイズ計算

```python
size = order.size
if -1 < size < 1:
    if not self._hedging:
        # 反対ポジション
        opposite_position = sum(
            trade.size for trade in self.trades
            if trade.code == order.code and trade.is_long != order.is_long
        )

        # 同方向ポジション（新規追加）
        same_direction_position = sum(
            trade.size for trade in self.trades
            if trade.code == order.code and trade.is_long == order.is_long
        )

        if opposite_position:
            # 反対ポジション → 全クローズ
            size = -opposite_position
        elif same_direction_position:
            # 同方向ポジション → margin_availableで買い増し（新規）
            size = copysign(
                int((self.margin_available * self._leverage * abs(size))
                    // adjusted_price_plus_commission),
                size
            )
        else:
            # ポジションなし → equityで全力
            size = copysign(
                int((self.equity * self._leverage * abs(size))
                    // adjusted_price_plus_commission),
                size
            )
    else:
        # ヘッジングモード（既存動作）
        size = copysign(
            int((self.equity * self._leverage * abs(size))
                // adjusted_price_plus_commission),
            size
        )
```

### 2. `docs/plans/fix-relative-size-option-c.md`

期待動作表を更新：
- `buy(size省略) & ロング保有` → `margin_availableで買い増し`
- `sell(size省略) & ショート保有` → `margin_availableで売り増し`

### 3. `tests/test_relative_size_option_c.py`

新しいテストクラス `TestSameDirectionPositionAddition` を追加：
- `test_buy_adds_to_long_position_with_margin_available`
- `test_sell_adds_to_short_position_with_margin_available`
- `test_no_margin_available_shows_warning`

## 実装手順

1. [ ] `_broker.py` L312-337 を変更
2. [ ] `fix-relative-size-option-c.md` の期待動作表を更新
3. [ ] テストケースを追加
4. [ ] 既存テスト実行確認

## 検証方法

```bash
# テスト実行
cd C:\Users\sasai\Documents\BackcastPro
python -m pytest tests/test_relative_size_option_c.py -v

# 特定のテストのみ
python -m pytest tests/test_relative_size_option_c.py::TestSameDirectionPositionAddition -v
```

## 動作例

**シナリオ**: 100万円で30%（300株）のロングポジション保有中に `buy()` 実行

```
1. same_direction_position = 300（同方向ポジションあり）
2. margin_available ≒ 70万円（資産 - 使用済みマージン）
3. size = 70万円 * 1 / 1000円 ≒ 700株
4. 結果: 300株 + 700株 = 1000株のロングポジション
```

---

## ヘッジングモード廃止

### 廃止理由
- `hedging=True` のテストカバレッジがない
- 複雑性を減らしてコードを簡潔にする
- FIFO方式が標準的なバックテスト動作

### 削除対象

#### 1. `src/BackcastPro/backtest.py`
- L63-65: Backtest クラス docstring から hedging 説明を削除
- L84: コンストラクタから `hedging=False` パラメータ削除
- L105: `partial` への `hedging=hedging` 引き渡し削除

#### 2. `src/BackcastPro/_broker.py`
- L42-45: ドキュメントから hedging 説明削除
- L56-57: コンストラクタから `hedging` パラメータ削除
- L82: `self._hedging = hedging` 削除
- L313: `if not self._hedging:` を削除（常にFIFO）
- L344-350: `else:` ブロック（ヘッジングモード処理）削除
- L362: `if not self._hedging:` を削除（常にFIFO処理実行）

### 変更後のコード構造

```python
# _broker.py 相対サイズ処理（簡略化後）
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
        # 反対ポジション → 全クローズ
        size = -opposite_position
    elif same_direction_position:
        # 同方向ポジション → margin_availableで買い増し
        size = copysign(
            int((self.margin_available * self._leverage * abs(size))
                // adjusted_price_plus_commission),
            size
        )
    else:
        # ポジションなし → equityで全力
        size = copysign(
            int((self.equity * self._leverage * abs(size))
                // adjusted_price_plus_commission),
            size
        )
```

```python
# _broker.py FIFO処理（簡略化後）
# 既存の反対方向の取引をFIFOでクローズ/削減
for trade in list(self.trades):
    if trade.is_long == order.is_long or trade.code != order.code:
        continue
    # ... FIFO処理
```

### 実装手順（追加）

5. [ ] `backtest.py` から `hedging` パラメータ削除
6. [ ] `_broker.py` から `_hedging` 属性と関連ロジック削除
7. [ ] 既存テストが全てパスすることを確認

### 破壊的変更

- `Backtest(..., hedging=True)` を使用しているコードは動作しなくなる
- 既存のテストには `hedging=True` を使用しているものがないため影響なし
