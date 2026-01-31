"""
marimoでインジケーターを表示するサンプル

実行方法:
marimo edit examples/marimo_test_indicators.py
"""
import marimo

__generated_with = "0.10.14"
app = marimo.App()


@app.cell
def __():
    import marimo as mo
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta
    return datetime, mo, np, pd, timedelta


@app.cell
def __(datetime, np, pd, timedelta):
    # テストデータ生成
    def generate_test_data(days=100):
        """テスト用の株価データを生成"""
        dates = pd.date_range(
            start=datetime.now() - timedelta(days=days), periods=days, freq="D"
        )

        # ランダムウォークで株価を生成
        np.random.seed(42)
        price = 100
        prices = []

        for _ in range(days):
            change = np.random.randn() * 2
            price = price * (1 + change / 100)
            prices.append(price)

        df = pd.DataFrame(
            {
                "Open": prices,
                "High": [p * 1.02 for p in prices],
                "Low": [p * 0.98 for p in prices],
                "Close": prices,
                "Volume": np.random.randint(1000000, 10000000, days),
            },
            index=dates,
        )

        # SMAを計算
        df["SMA_20"] = df["Close"].rolling(20).mean()
        df["SMA_50"] = df["Close"].rolling(50).mean()

        return df

    df = generate_test_data(100)
    return df, generate_test_data


@app.cell
def __(df):
    # BackcastProをインポート
    import sys
    sys.path.insert(0, "../src")
    from BackcastPro import Backtest

    bt = Backtest(data={"TEST": df}, cash=100000)
    return Backtest, bt, sys


@app.cell
def __(mo):
    mo.md(
        """
        # インジケーター表示機能のテスト

        BackcastProのチャートにSMAなどのテクニカルインジケーターを追加表示できます。
        """
    )
    return


@app.cell
def __(mo):
    mo.md("## 基本的な使い方")
    return


@app.cell
def __(bt):
    # 基本的なインジケーター表示
    chart1 = bt.chart(code="TEST", indicators=["SMA_20", "SMA_50"])
    chart1
    return (chart1,)


@app.cell
def __(mo):
    mo.md("## カスタムカラーとスタイル")
    return


@app.cell
def __(bt):
    # カスタムカラー
    chart2 = bt.chart(
        code="TEST",
        indicators=["SMA_20", "SMA_50"],
        indicator_options={
            "SMA_20": {"color": "#2196F3", "lineWidth": 2, "title": "20日移動平均"},
            "SMA_50": {"color": "#FFC107", "lineWidth": 3, "title": "50日移動平均"},
        },
    )
    chart2
    return (chart2,)


@app.cell
def __(mo):
    mo.md("## リプレイモードでの動作確認")
    return


@app.cell
def __(bt, mo):
    slider = mo.ui.slider(start=1, stop=len(bt.index), value=50, label="時間", step=1)
    slider
    return (slider,)


@app.cell
def __(bt, slider):
    # リプレイモードでインジケーターを表示
    bt.goto(slider.value)
    chart3 = bt.chart(code="TEST", indicators=["SMA_20", "SMA_50"])
    chart3
    return (chart3,)


@app.cell
def __(mo):
    mo.md(
        """
        ---
        ## データ確認

        DataFrameにSMAカラムが追加されていることを確認
        """
    )
    return


@app.cell
def __(df):
    df.tail(20)
    return


if __name__ == "__main__":
    app.run()
