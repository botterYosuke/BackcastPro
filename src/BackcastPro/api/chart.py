# -*- coding: utf-8 -*-
import datetime
import pandas as pd
import plotly.graph_objects as go


def chart(code: str = "", from_: datetime = None, to: datetime = None,
            df: pd.DataFrame = None, title: str = None) -> pd.DataFrame | None:
    """
    株価データを指定して株価チャートを表示する（plotly使用）
    
    Args:
        code: 銘柄コード（例: "6723"）
        from_: 開始日（datetime, オプション）
        to: 終了日（datetime, オプション）
        df: 株価データ（pandas DataFrame）
        title: チャートのタイトル（オプション）
    """
    if df is None:
        return chart_by_code(code, from_, to, title=title)

    chart_by_df(df, title=title)
    return None 


def chart_by_code(code: str, from_: datetime = None, to: datetime = None, title: str = None) -> pd.DataFrame:
    """
    銘柄コードを指定して株価チャートを表示する（plotly使用）

    Args:
        code: 銘柄コード（例: "6723"）
        from_: 開始日（datetime, オプション）
        to: 終了日（datetime, オプション）
        title: チャートのタイトル（オプション）

    Raises:
        NameError: get_stock_price関数が存在しない場合
        ValueError: データが空の場合、または必要なカラムが存在しない場合
    """

    # 株価データを取得
    from .stocks_daily import stocks_price
    __sp__ = stocks_price()
    df = __sp__.get_japanese_stock_price_data(code, from_=from_, to=to)

    chart_by_df(df, title=title)

    return df

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

def chart_by_df(df: pd.DataFrame, title: str = None) -> None:
    """株価データを指定して株価チャートを表示する（plotly使用）"""
    # Codeを取得（データ整形前に取得）
    code = None
    if 'Code' in df.columns:
        code = df.iloc[0]['Code']
    elif 'code' in df.columns:
        code = df.iloc[0]['code']
    
    # データを整形
    df = _prepare_chart_df(df)
    
    if df.empty:
        print("データが空です。")
        return
    
    # チャートタイトルを決定
    chart_title = title if title else (code if code else "Candlestick with Volume")
    
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
        title=chart_title,
        yaxis=dict(title="Price"),
        yaxis2=dict(
            title="Volume",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        xaxis_rangeslider_visible=False,
    )
    
    fig.show()
