# -*- coding: utf-8 -*-
import datetime
import pandas as pd
import plotly.graph_objects as go


def chart(code: str = "", from_: datetime = None, to: datetime = None,
            df: pd.DataFrame = None):
    """
    株価データを指定して株価チャートを表示する（plotly使用）
    
    Args:
        code: 銘柄コード（例: "6723"）
        from_: 開始日（datetime, オプション）
        to: 終了日（datetime, オプション）
        df: 株価データ（pandas DataFrame）
    """
    if df is None:
        # 株価データを取得
        from .stocks_daily import stocks_price
        __sp__ = stocks_price()
        df = __sp__.get_japanese_stock_price_data(code, from_=from_, to=to)


    # データが空の場合のエラーハンドリング
    if df.empty:
        raise ValueError(f"銘柄コード '{code}' の株価が取得できませんでした。")
            
    return chart_by_df(df)


def _prepare_chart_df(df: pd.DataFrame) -> pd.DataFrame:
    """チャート表示用データを準備（plotly用）"""
    # indexがDatetimeIndexの場合は、Date列として復元
    if isinstance(df.index, pd.DatetimeIndex):
        # 元のindex名を保存（reset_index()の前に確認）
        original_index_name = df.index.name
        # DatetimeIndexをDate列として復元
        df = df.reset_index()
        # 復元された列の名前が'Date'でない場合は'Date'にリネーム
        # 名前のないDatetimeIndexは'index'という名前で復元される
        # 名前がある場合はその名前で復元される
        if original_index_name is None or original_index_name == '':
            # 名前のないDatetimeIndexの場合、'index'という列名で復元される
            if 'index' in df.columns:
                df.rename(columns={'index': 'Date'}, inplace=True)
        elif original_index_name != 'Date':
            # index名が'Date'でない場合、その名前で復元されているので'Date'にリネーム
            if original_index_name in df.columns:
                df.rename(columns={original_index_name: 'Date'}, inplace=True)
    else:
        # インデックスをリセット（DatetimeIndexでない場合）
        df = df.reset_index()
    
    # Date カラムを判定
    date_col = 'Date' if 'Date' in df.columns else df.columns[0]
    df['Date'] = pd.to_datetime(df[date_col])
    
    # カラム名を大文字に統一（plotly用）
    column_mapping = {
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume',
        'date': 'Date'
    }
    # 小文字に変換してからマッピング
    df.columns = df.columns.str.lower()
    df.rename(columns=column_mapping, inplace=True)
    
    # 必要なカラムを抽出して数値変換
    required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
    available_cols = [col for col in required_cols if col in df.columns]
    df = df[available_cols].copy()
    
    # 数値カラムを数値型に変換
    numeric_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    return df.dropna()

def chart_by_df(df: pd.DataFrame):
    """
    株価データを指定して株価チャートを表示する（plotly使用）

    Args:
        df: 株価データ（pandas DataFrame）
    """

    # データを整形
    df = _prepare_chart_df(df)    

    # plotlyのFigureを作成
    fig = go.Figure()
    
    # ローソク足
    fig.add_trace(
        go.Candlestick(
            x=df["Date"],
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Price",
        )
    )
    
    # 出来高（棒）
    fig.add_trace(
        go.Bar(
            x=df["Date"],
            y=df["Volume"],
            name="Volume",
            yaxis="y2",
        )
    )
    
    # レイアウト設定
    fig.update_layout(
        yaxis=dict(title="Price"),
        yaxis2=dict(
            title="Volume",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        xaxis_rangeslider_visible=False,
    )
    
    return fig
