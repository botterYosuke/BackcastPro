from math import nan
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import pandas as pd
import pandas_datareader.data as web

from BackcastPro import Strategy
from SmaCross import crossover, SMA
from Plotting import plot

class SmaCross(Strategy):
    # Define the two MA lags as *class variables*
    # for later optimization
    n1 = 10
    n2 = 20
    
    def init(self):
        for code, df in self.data.items():
            # Precompute the two moving averages and add to data
            df['sma1'] = SMA(df.Close, self.n1)
            df['sma2'] = SMA(df.Close, self.n2)
            
    
    def next(self, current_time):
        """
        このタイミングは、寄り付き前です。
        日足データを扱う場合:
        ここで注文を出したら、寄り付き(Open)から大引け(Close)まで
        同じ注文が出されます。
        
        Args:
            current_time: 現在のタイムスタンプ
        """

        for code, df in self.data.items():
            # 移動平均が有効な値を持つまでスキップ
            if pd.isna(df.sma1.iloc[-1]) or pd.isna(df.sma2.iloc[-1]):
                continue

            # 5If sma1 crosses above sma2, close any existing
            # short trades, and buy the asset
            if crossover(df.sma1, df.sma2):
                self.position.close()
                self.buy(code=code)

            # Else, if sma1 crosses below sma2, close any existing
            # long trades, and sell the asset
            elif crossover(df.sma2, df.sma1):
                self.position.close()
                self.sell(code=code)


# データ取得とバックテスト実行
from BackcastPro import Backtest

# データ取得
TOYOTA = '7203.JP'  # トヨタ
SONY = '6758.JP'    # ソニー
target = {
    TOYOTA: web.DataReader(TOYOTA, 'stooq'),
    SONY: web.DataReader(SONY, 'stooq')    
}
bt = Backtest(target, SmaCross, cash=10_000, commission=.002, finalize_trades=True)
stats = bt.run()
print(stats)


# streamlit run で実行されている時のみ実行
try:
    import streamlit as st
    if st.runtime.exists():
        page_title = os.path.splitext(os.path.basename(__file__))[0]
        plot(page_title, bt)
    else:
        print("Streamlit環境で実行されていません。通常のPython実行です。")
except ImportError:
    print("Streamlitがインストールされていません。")



