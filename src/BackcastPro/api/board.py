# -*- coding: utf-8 -*-
import datetime
import pandas as pd
import numpy as np
import plotly.graph_objects as go


def board(code: str = "", date: datetime = None,
            df: pd.DataFrame = None):
    """
    銘柄コードを指定して板情報チャートを表示する
    
    Args:
        code: 銘柄コード（例: "6363"）
    
    Raises:
        NameError: get_stock_board関数が存在しない場合
        ValueError: データが空の場合、または必要なカラムが存在しない場合
    """
    if df is None:
        # 板情報データを取得
        from .stocks_board import stocks_board
        __sb__ = stocks_board()    
        df = __sb__.get_japanese_stock_board_data(code, date)

    # データが空の場合のエラーハンドリング
    if df.empty:
        raise ValueError(f"銘柄コード '{code}' の板情報が取得できませんでした。")

    return board_by_df(df)


def board_by_df(df: pd.DataFrame):
    """
    板情報データを指定して板情報チャートを表示する（plotly使用）

    Args:
        df: 板情報データ（pandas DataFrame）
    """

    # 必要なカラムの存在確認
    required_cols = ['Price', 'Qty', 'Type']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"必要なカラムが見つかりません: {missing_cols}。利用可能なカラム: {list(df.columns)}")

    # データの準備
    df_filtered = df[df['Price'] > 0].copy()
    df_filtered = df_filtered.sort_values('Price', ascending=False)

    # データが空になった場合のエラーハンドリング
    if df_filtered.empty:
        raise ValueError(f"有効な板情報データがありませんでした。")

    # 買い板（Bid）と売り板（Ask）のデータを分離
    bid_data = df_filtered[df_filtered['Type'] == 'Bid']
    ask_data = df_filtered[df_filtered['Type'] == 'Ask']

    # 買い板または売り板のデータが存在しない場合のエラーハンドリング
    if len(bid_data) == 0 and len(ask_data) == 0:
        raise ValueError(f"買い板または売り板のデータが見つかりませんでした。")

    # すべての価格を統合してユニークな価格リストを作成（価格順にソート）
    all_prices = sorted(df_filtered['Price'].unique(), reverse=True)

    # plotlyのFigureを作成
    fig = go.Figure()

    # 買い板のデータをプロット（右側に表示）
    if len(bid_data) > 0:
        # 価格でソート（昇順）
        bid_data_sorted = bid_data.sort_values('Price')
        fig.add_trace(
            go.Bar(
                y=[f"{price:,.0f}円" for price in bid_data_sorted['Price']],
                x=bid_data_sorted['Qty'],
                name='買い板',
                orientation='h',
                marker=dict(color='#2196F3', line=dict(color='#1976D2', width=1)),
                text=[f"{qty:,.0f}" for qty in bid_data_sorted['Qty']],
                textposition='outside',
                hovertemplate='価格: %{y}<br>数量: %{x:,.0f}株<extra></extra>'
            )
        )

    # 売り板のデータをプロット（左側に表示、負の値で表示）
    if len(ask_data) > 0:
        # 価格でソート（昇順）
        ask_data_sorted = ask_data.sort_values('Price')
        fig.add_trace(
            go.Bar(
                y=[f"{price:,.0f}円" for price in ask_data_sorted['Price']],
                x=-ask_data_sorted['Qty'],
                name='売り板',
                orientation='h',
                marker=dict(color='#F44336', line=dict(color='#D32F2F', width=1)),
                text=[f"{qty:,.0f}" for qty in ask_data_sorted['Qty']],
                textposition='outside',
                hovertemplate='価格: %{y}<br>数量: %{x:,.0f}株<extra></extra>'
            )
        )

    # 銘柄コードを取得（board関数から呼び出された場合のみ）
    # board_by_df単体で呼ばれた場合はタイトルに銘柄コードを含めない
    title_text = '板情報チャート'

    # レイアウト設定
    fig.update_layout(
        title=dict(text=title_text, font=dict(size=14), x=0.5, xanchor='center'),
        xaxis=dict(
            title='数量（株）',
            gridcolor='rgba(0,0,0,0.1)',
            gridwidth=1,
            zeroline=True,
            zerolinecolor='black',
            zerolinewidth=2
        ),
        yaxis=dict(
            title='価格（円）',
            categoryorder='array',
            categoryarray=[f"{price:,.0f}円" for price in all_prices]
        ),
        barmode='overlay',
        height=600,
        hovermode='closest',
        showlegend=True,
        legend=dict(x=1, y=1, xanchor='right', yanchor='top')
    )

    return fig
