# Lightweight Chart 更新問題の修正

## 概要

**日付**: 2026-01-27
**対象ファイル**: `src/BackcastPro/backtest.py`
**関連**: marimo ノートブックでの chart 表示

---

## 問題の内容

### 現象

marimo ノートブックで以下の順序でセルを実行すると、チャートが更新されない：

1. `bt.chart(code=code)` を実行 → 空のチャートが表示される
2. `run()` を実行 → `step()` が実行されるが、チャートは更新されない
3. 再度 `bt.chart(code=code)` を実行 → チャートが正しく表示される

**期待される動作**: `run()` 実行後、自動的にチャートが更新されるべき

---

## 調査でわかったこと

### 1. marimo のセル実行順序

marimo は依存関係に基づいてセルを並列実行する。そのため：

- `Cell-5: bt.chart()` と `Cell-6: run()` が同時に実行される
- `bt.chart()` が先に完了し、`run()` → `step()` がまだ実行されていない状態

### 2. `_data` と `_current_data` の違い

| 変数 | 設定タイミング | 内容 |
|------|---------------|------|
| `_data` | `set_data()` | 全期間の株価データ |
| `_current_data` | `step()` | 現在ステップまでのデータ |

`step()` が実行されるまで `_current_data` は空のまま。

### 3. `chart()` の EARLY RETURN 問題

```python
# 修正前のコード
if code not in self._current_data or len(self._current_data[code]) == 0:
    return LightweightChartWidget()  # 空のウィジェットを返す（キャッシュ登録なし）
```

EARLY RETURN 時に返されるウィジェットは `_chart_widgets` に登録されていなかった。

### 4. `_update_all_charts()` の動作

```python
def _update_all_charts(self) -> None:
    for code, widget in self._chart_widgets.items():  # _chart_widgets が空なら何もしない
        self.update_chart(widget, code)
```

`_chart_widgets` が空の場合、`step()` 後の自動更新が機能しない。

### 5. 初期状態の問題

```python
get_playing, set_playing = mo.state(True)  # 初期値が True
```

起動時に `run()` が呼ばれると：
- `get_playing() == True` なので `set_playing(False)` するだけ
- `_game_loop` は開始されず、`step()` は実行されない

---

## 問題の流れ（修正前）

```
1. Cell-5: bt.chart(code) 実行
   └─ _current_data が空 → EARLY RETURN
   └─ 空のウィジェットを返す（_chart_widgets に登録されない）

2. Cell-6: run() 実行
   └─ get_playing() == True なので set_playing(False) のみ
   └─ _game_loop は開始されない

3. 2回目の run() 実行（ユーザー操作）
   └─ get_playing() == False なので _game_loop 開始
   └─ step() → _update_all_charts()
   └─ _chart_widgets が空なので何も更新されない

4. Cell-5 再実行
   └─ _current_data にデータがある
   └─ 正しいウィジェット作成 → _chart_widgets に登録
   └─ チャートが表示される
```

---

## 施した対応内容

### 修正箇所: `backtest.py` の `chart()` メソッド

EARLY RETURN 時もウィジェットを `_chart_widgets` に登録するように変更：

```python
# 修正後のコード
if not self._is_started or self._broker_instance is None:
    from .api.chart import LightweightChartWidget
    # キャッシュに登録して後から更新できるようにする
    if code not in self._chart_widgets:
        self._chart_widgets[code] = LightweightChartWidget()
    return self._chart_widgets[code]

if code not in self._current_data or len(self._current_data[code]) == 0:
    from .api.chart import LightweightChartWidget
    # キャッシュに登録して後から更新できるようにする
    if code not in self._chart_widgets:
        self._chart_widgets[code] = LightweightChartWidget()
    return self._chart_widgets[code]
```

---

## 修正後の流れ

```
1. Cell-5: bt.chart(code) 実行
   └─ _current_data が空 → EARLY RETURN
   └─ 空のウィジェットを作成し _chart_widgets に登録 ★
   └─ 同じウィジェットを返す

2. run() → step() → _update_all_charts()
   └─ _chart_widgets['7203'] が存在する ★
   └─ update_chart() でウィジェットを更新
   └─ 同じウィジェットインスタンスなので Cell-5 の表示も更新される
```

---

## 検証方法

1. marimo で fintech1.py を開く
2. 全セルを実行（自動実行）
3. チャートが自動的に更新されることを確認

---

## 検討した他の解決策

| 案 | 内容 | 採用 |
|----|------|------|
| 案1 | EARLY RETURN でもキャッシュ登録 | ✅ 採用 |
| 案2 | Cell-5 を AutoRefresh に依存させる | - |
| 案3 | `mo.state(True)` を `mo.state(False)` に変更 | - |

案1 を採用した理由：
- backtest.py のみの修正で済む
- ノートブック側の変更が不要
- 同じウィジェットインスタンスを再利用するため、marimo のリアクティブシステムと整合性がある

---

## 関連ファイル

- `src/BackcastPro/backtest.py` - 修正対象
- `src/BackcastPro/api/chart.py` - LightweightChartWidget の実装
- サンプルノートブック: `C:\Users\sasai\AppData\Local\Temp\fintech1.py`

---

## 今後の注意点

1. `chart()` メソッドを変更する際は、EARLY RETURN パスでもキャッシュ登録が行われることを考慮する
2. `_chart_widgets` のライフサイクルは `reset(clear_chart_cache=True)` でクリアされる
3. marimo のセル実行順序は依存関係に基づくため、`step()` 前に `chart()` が呼ばれる可能性を常に考慮する
