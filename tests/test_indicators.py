"""
インジケーター表示機能のテストサンプル

このスクリプトは、BackcastProのチャート機能にSMAなどの
テクニカルインジケーターを追加表示する機能をテストします。
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# BackcastProをインポート
import sys
sys.path.insert(0, "../src")

from BackcastPro import Backtest

# テストデータ生成
def generate_test_data(days=100):
    """テスト用の株価データを生成"""
    dates = pd.date_range(start=datetime.now() - timedelta(days=days), periods=days, freq='D')

    # ランダムウォークで株価を生成
    np.random.seed(42)
    price = 100
    prices = []

    for _ in range(days):
        change = np.random.randn() * 2
        price = price * (1 + change / 100)
        prices.append(price)

    df = pd.DataFrame({
        'Open': prices,
        'High': [p * 1.02 for p in prices],
        'Low': [p * 0.98 for p in prices],
        'Close': prices,
        'Volume': np.random.randint(1000000, 10000000, days)
    }, index=dates)

    # SMAを計算
    df['SMA_20'] = df['Close'].rolling(20).mean()
    df['SMA_50'] = df['Close'].rolling(50).mean()

    return df

# テストケース1: 基本的な使い方
print("テストケース1: 基本的なインジケーター表示")
df = generate_test_data(100)

bt = Backtest(data={"TEST": df}, cash=100000)

# インジケーター付きでチャート表示
chart = bt.chart(code="TEST", indicators=['SMA_20', 'SMA_50'])
print("✓ chart()でインジケーター付きチャートを作成")

# テストケース2: カスタムカラー
print("\nテストケース2: カスタムカラーとスタイル")
chart2 = bt.chart(
    code="TEST",
    indicators=['SMA_20', 'SMA_50'],
    indicator_options={
        'SMA_20': {'color': '#2196F3', 'lineWidth': 2, 'title': '20日移動平均'},
        'SMA_50': {'color': '#FFC107', 'lineWidth': 3, 'title': '50日移動平均'}
    }
)
print("✓ カスタムカラーとスタイルでチャートを作成")

# テストケース3: chart_by_dfで直接表示
print("\nテストケース3: chart_by_dfで直接表示")
from BackcastPro import chart_by_df

chart3 = chart_by_df(
    df,
    indicators=['SMA_20', 'SMA_50'],
    height=600
)
print("✓ chart_by_df()でインジケーター付きチャートを作成")

# テストケース4: NaN値のハンドリング
print("\nテストケース4: NaN値のハンドリング")
df_with_nan = generate_test_data(30)  # 短いデータでSMA_50がNaNになる
chart4 = bt.chart(code="TEST", indicators=['SMA_20', 'SMA_50'])
print("✓ NaN値を含むインジケーターでもエラーなく表示")

# テストケース5: 存在しないカラムを指定
print("\nテストケース5: 存在しないカラムの処理")
chart5 = bt.chart(code="TEST", indicators=['SMA_20', 'NonExistent'])
print("✓ 存在しないカラムを指定してもエラーなく表示")

print("\n✅ すべてのテストケースが完了しました！")
print("\nmarimoで実際にチャートを確認するには:")
print("marimo edit tests/marimo_test_indicators.py")
