# 作業依頼: 自動再生スイッチのUI状態が更新されない問題

## 概要

`fintech1.py` の自動再生機能は動作するようになったが、UIのスイッチが ON 状態を反映しない。

## 対象ファイル

`C:\Users\sasai\AppData\Local\Temp\fintech1.py`

## 現在の問題

`toggle_run()` を実行すると:
- ✅ 自動再生は動作する（`bt.step()` が500msごとに呼ばれてチャートが更新される）
- ❌ スイッチのUIがOFFのまま（`set_playing(True)` を呼んでもスイッチの見た目が変わらない）

## 原因

```python
_play_switch = mo.ui.switch(label="自動再生", value=get_playing())
```

スイッチの `value` は初期化時の `get_playing()` の値（False）で固定されている。
`set_playing(True)` を呼んでも、スイッチのUI自体は再作成されないため、見た目が更新されない。

## 修正方針

marimoでスイッチとstateを同期させるには、以下のいずれかの方法がある:

### 方法1: スイッチの `on_change` でstateを更新し、stateの変更でスイッチを再作成

```python
@app.cell
def _():
    import marimo as mo

    get_playing, set_playing = mo.state(False)
    return get_playing, set_playing, mo

@app.cell
def _(get_playing, set_playing, mo):
    # get_playing() に依存させることで、state変更時に再作成される
    _play_switch = mo.ui.switch(
        label="自動再生",
        value=get_playing(),
        on_change=lambda v: set_playing(v)
    )
    _play_switch
    return (_play_switch,)
```

### 方法2: スイッチの値を直接使う（stateを使わない）

```python
@app.cell
def _(mo):
    play_switch = mo.ui.switch(label="自動再生")
    play_switch
    return (play_switch,)

@app.cell
def _(play_switch, bt, mo):
    # スイッチの値に依存
    if play_switch.value:
        mo.Thread(target=_game_loop).start()
```

## 検証方法

1. `marimo edit C:\Users\sasai\AppData\Local\Temp\fintech1.py`
2. スイッチをONにする
3. 自動再生が開始され、スイッチがON状態を維持することを確認
4. スイッチをOFFにする
5. 自動再生が停止することを確認

## 関連情報

- marimo公式ドキュメント: https://docs.marimo.io/guides/state/
- `mo.state()` のリアクティビティ: stateが変更されると、そのstateを参照するセルが再実行される
