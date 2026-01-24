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

def chart_by_df(
    df: pd.DataFrame,
    *,
    trades: list = None,
    height: int = 500,
    show_tags: bool = True,
    show_volume: bool = True,
    title: str = None,
    code: str = None,
):
    """
    株価データを指定して株価チャートを表示する（plotly使用）

    Args:
        df: 株価データ（pandas DataFrame）
        trades: 取引リスト（Trade オブジェクトのリスト）。各オブジェクトは以下のプロパティを持つ:
                - code: 銘柄コード
                - size: ポジションサイズ（正: ロング、負: ショート）
                - entry_time: エントリー日時
                - entry_price: エントリー価格
                - tag: 売買理由（オプション）
                - exit_time: 決済日時（オプション）
                - exit_price: 決済価格（オプション）
        height: チャートの高さ（ピクセル）
        show_tags: 売買理由（tag）をチャートに表示するか
        show_volume: 出来高を表示するか
        title: チャートのタイトル
        code: 銘柄コード（trades のフィルタリング用）
    """
    # データを整形
    df = _prepare_chart_df(df)
    x_data = df["Date"]
    volume_col = df.get("Volume", None)

    # plotlyのFigureを作成
    fig = go.Figure()

    # ローソク足
    fig.add_trace(
        go.Candlestick(
            x=x_data,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name=code or "Price",
        )
    )

    # 出来高（棒）
    if show_volume and volume_col is not None:
        fig.add_trace(
            go.Bar(
                x=x_data,
                y=volume_col,
                name="Volume",
                yaxis="y2",
            )
        )

    # 売買マーカー
    if trades:
        for trade in trades:
            # codeが指定されている場合はフィルタリング
            if code is not None and hasattr(trade, 'code') and trade.code != code:
                continue

            is_long = trade.size > 0

            # エントリーマーカー
            hover_text = f"{'BUY' if is_long else 'SELL'}<br>Price: {trade.entry_price:.2f}"
            tag = getattr(trade, 'tag', None)
            if show_tags and tag:
                hover_text += f"<br>Reason: {tag}"

            fig.add_trace(go.Scatter(
                x=[trade.entry_time],
                y=[trade.entry_price],
                mode="markers+text" if show_tags and tag else "markers",
                marker=dict(
                    color="green" if is_long else "red",
                    size=12,
                    symbol="triangle-up" if is_long else "triangle-down",
                ),
                text=[tag] if show_tags and tag else None,
                textposition="top center" if is_long else "bottom center",
                textfont=dict(size=10),
                hovertext=hover_text,
                hoverinfo="text",
                name="BUY" if is_long else "SELL",
                showlegend=False
            ))

            # イグジットマーカー（決済済みの場合）
            exit_time = getattr(trade, 'exit_time', None)
            exit_price = getattr(trade, 'exit_price', None)
            if exit_time is not None and exit_price is not None:
                pnl = (exit_price - trade.entry_price) * trade.size
                fig.add_trace(go.Scatter(
                    x=[exit_time],
                    y=[exit_price],
                    mode="markers",
                    marker=dict(
                        color="blue",
                        size=10,
                        symbol="x",
                    ),
                    hovertext=f"EXIT<br>Price: {exit_price:.2f}<br>PnL: {pnl:+.2f}",
                    hoverinfo="text",
                    name="EXIT",
                    showlegend=False
                ))

    # レイアウト設定
    layout_config = {
        "yaxis": dict(title="Price"),
        "xaxis_rangeslider_visible": False,
        "height": height,
    }

    if show_volume and volume_col is not None:
        layout_config["yaxis2"] = dict(
            title="Volume",
            overlaying="y",
            side="right",
            showgrid=False,
        )

    if title:
        layout_config["title"] = title
        layout_config["xaxis_title"] = "Date"
        layout_config["yaxis_title"] = "Price"

    fig.update_layout(**layout_config)

    return fig
