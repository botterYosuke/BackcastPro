"""
BackcastPro + marimo リプレイ型シミュレーター サンプル

使い方:
    marimo edit marimo_replay.py
    または
    marimo run marimo_replay.py
"""

import marimo

__generated_with = "0.10.0"
app = marimo.App(width="full")


@app.cell
def __():
    import marimo as mo
    import pandas as pd
    import yfinance as yf
    from datetime import datetime, timedelta
    return datetime, mo, pd, timedelta, yf


@app.cell
def __(datetime, timedelta, yf):
    # データ取得
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)

    code = "7203.T"  # トヨタ（東証）
    df = yf.download(code, start=start_date, end=end_date, progress=False)

    print(f"データ取得完了: {code} ({len(df)} 件)")
    return code, df, end_date, start_date


@app.cell
def __(code, df):
    from BackcastPro import Backtest

    # バックテスト初期化
    bt = Backtest(
        data={code: df},
        cash=100_000,
        commission=0.001,
        finalize_trades=True,
    )

    print(f"バックテスト初期化完了: {len(bt.index)} ステップ")
    return Backtest, bt


@app.cell
def __():
    # 戦略定義: 前日比で売買
    def my_strategy(bt):
        """
        シンプルな戦略:
        - 前日比下落 → 買い
        - 前日比上昇 & ポジションあり → 売り
        """
        for code, df in bt.data.items():
            if len(df) < 2:
                continue

            c0 = df["Close"].iloc[-2]
            c1 = df["Close"].iloc[-1]

            pos = bt.position_of(code)

            if pos == 0 and c1 < c0:
                bt.buy(code=code, tag="dip_buy")
            elif pos > 0 and c1 > c0:
                bt.sell(code=code, tag="profit_take")

    return (my_strategy,)


@app.cell
def __(bt, mo):
    # 時間スライダー
    slider = mo.ui.slider(
        start=1,
        stop=len(bt.index),
        value=1,
        label="時間",
        show_value=True,
        full_width=True,
    )
    slider
    return (slider,)


@app.cell
def __(bt, code, mo, my_strategy, slider):
    # スライダー位置まで進める
    bt.goto(slider.value, strategy=my_strategy)

    # チャート生成
    chart = bt.chart(code=code, height=500, show_tags=True)

    # 情報パネル
    info = mo.md(f"""
    ## 状況

    | 項目 | 値 |
    |------|-----|
    | 日時 | {bt.current_time} |
    | 進捗 | {bt.progress * 100:.1f}% ({bt._step_index}/{len(bt.index)}) |
    | 資産 | ¥{bt.equity:,.0f} |
    | 現金 | ¥{bt.cash:,.0f} |
    | ポジション | {bt.position_of(code)} 株 |
    | 決済済取引 | {len(bt.closed_trades)} 件 |
    """)

    mo.vstack([chart, info])
    return chart, info


@app.cell
def __(bt, mo):
    # 取引履歴テーブル
    if bt.closed_trades:
        import pandas as pd

        trades_data = []
        for t in bt.closed_trades:
            trades_data.append({
                "銘柄": t.code,
                "方向": "買" if t.size > 0 else "売",
                "数量": abs(t.size),
                "エントリー": t.entry_time,
                "エントリー価格": f"¥{t.entry_price:,.0f}",
                "イグジット": t.exit_time,
                "イグジット価格": f"¥{t.exit_price:,.0f}",
                "損益": f"¥{t.pl:+,.0f}",
                "理由": t.tag or "-",
            })

        trades_df = pd.DataFrame(trades_data)
        mo.md("## 取引履歴")
        mo.ui.table(trades_df)
    else:
        mo.md("_まだ取引がありません_")
    return


@app.cell
def __(bt, mo, my_strategy):
    # 最後まで実行ボタン
    def run_to_end(_):
        bt.reset()
        while not bt.is_finished:
            my_strategy(bt)
            bt.step()
        return bt.finalize()

    run_button = mo.ui.button(
        label="最後まで実行",
        on_click=run_to_end,
    )

    mo.hstack([run_button, mo.md("← クリックで全期間を一括実行")])
    return run_button, run_to_end


if __name__ == "__main__":
    app.run()
