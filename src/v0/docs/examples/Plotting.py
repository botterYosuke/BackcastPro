import pandas as pd
import pandas_datareader.data as web

from datetime import datetime, timedelta

import streamlit as st

from BackcastPro import Backtest


def plot(page_title: str, bt: Backtest) -> None:

    st.set_page_config(page_title=page_title, layout='wide')
    st.title(f'{page_title} - Streamlit')

    stats = bt._results
    code, df = next(iter(bt._data.items()))

    with st.sidebar:
        st.header('設定')
        code = st.text_input('銘柄コード', value=code)
        years = st.slider('取得年数', min_value=1, max_value=10, value=1)
        cash = st.number_input('初期資金', value=bt.cash, step=1000)
        commission = st.number_input('手数料（率）', value=bt.commission, step=0.001, format='%.4f')
        run = st.button('実行')

    if run:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * years)

        with st.spinner('データ取得中...'):
            df = web.DataReader(code, 'stooq', start_date, end_date)

        if df is None or len(df) == 0:
            st.error('データが取得できませんでした。コードや期間を確認してください。')
            st.stop()

        bt = Backtest({code: df}, bt._strategy, cash=cash, commission=commission)

        with st.spinner('バックテスト実行中...'):
            stats = bt.run()

    st.subheader('価格データ（終値）')
    st.line_chart(df[['Close']])

    # 成績表（Backtesting.pyの出力に相当）
    excluded = {'_strategy', '_equity_curve', '_trades'}
    scalar_stats = {}
    for k, v in stats.items():
        if k in excluded:
            continue
        if isinstance(v, (pd.DataFrame, pd.Series)):
            continue
        if hasattr(v, 'components') and hasattr(v, 'total_seconds'):
            # timedeltaを文字列化
            scalar_stats[k] = str(v)
        else:
            scalar_stats[k] = v

    st.subheader('成績サマリ')
    summary_df = pd.DataFrame(scalar_stats, index=[0]).T
    summary_df.columns = ['Value']
    # すべての値を文字列に変換してPyArrowエラーを回避
    summary_df['Value'] = summary_df['Value'].astype(str)
    st.table(summary_df)

    # エクイティカーブとドローダウン
    st.subheader('エクイティ・ドローダウン')
    equity_df = stats['_equity_curve'][['Equity', 'DrawdownPct']]
    st.line_chart(equity_df)

    # トレード一覧
    st.subheader('トレード一覧')
    trades_df = stats['_trades']
    st.dataframe(trades_df)

    # 価格にエントリー/エグジットを重ねた簡易可視化
    st.subheader('価格とエントリー（簡易）')
    close = df['Close'].rename('Close')
    buy_points = pd.Series(index=df.index, dtype=float, name='Buy')
    sell_points = pd.Series(index=df.index, dtype=float, name='Sell')
    for row in trades_df.itertuples(index=False):
        if pd.notna(row.EntryTime):
            if row.Size > 0:
                buy_points.loc[row.EntryTime] = row.EntryPrice
            elif row.Size < 0:
                sell_points.loc[row.EntryTime] = row.EntryPrice
    plot_df = pd.concat([close, buy_points, sell_points], axis=1)
    st.line_chart(plot_df)


