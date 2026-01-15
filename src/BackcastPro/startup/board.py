# -*- coding: utf-8 -*-
import datetime
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import warnings

# 日本語フォントの設定（Windows環境）
# MS Gothic、MS Mincho、Yu Gothic などが利用可能
matplotlib.rcParams['font.family'] = 'MS Gothic'  # または 'MS Mincho', 'Yu Gothic'
# 警告を抑制（オプション）
warnings.filterwarnings('ignore', category=UserWarning)


def board(code):
    """
    銘柄コードを指定して板情報チャートを表示する
    
    Args:
        code: 銘柄コード（例: "6363"）
    
    Raises:
        NameError: get_stock_board関数が存在しない場合
        ValueError: データが空の場合、または必要なカラムが存在しない場合
    """
    # 板情報データを取得
    from ..api.stocks_board import stocks_board
    __sb__ = stocks_board()    
    df = __sb__.get_japanese_stock_board_data(code)
    
    # データが空の場合のエラーハンドリング
    if df.empty:
        raise ValueError(f"銘柄コード '{code}' の板情報が取得できませんでした。")
    
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
    price_to_index = {price: idx for idx, price in enumerate(all_prices)}
    
    # 図のサイズを設定
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # 買い板のデータをプロット（右側に表示）
    if len(bid_data) > 0:
        # 価格に基づいてY軸位置を設定
        y_pos_bid = [price_to_index[price] for price in bid_data['Price']]
        ax.barh(y_pos_bid, bid_data['Qty'], 
                color='#2196F3', alpha=0.7, 
                label='買い板', edgecolor='#1976D2', linewidth=1)
        
        # 数量ラベルを追加
        max_qty = bid_data['Qty'].max() if len(bid_data) > 0 else 0
        for idx, row in bid_data.iterrows():
            y_pos = price_to_index[row['Price']]
            ax.text(row['Qty'] + max_qty * 0.01, y_pos, 
                    f"{row['Qty']:,.0f}", 
                    va='center', fontsize=9)
    
    # 売り板のデータをプロット（左側に表示、負の値で表示）
    if len(ask_data) > 0:
        # 価格に基づいてY軸位置を設定
        y_pos_ask = [price_to_index[price] for price in ask_data['Price']]
        ax.barh(y_pos_ask, -ask_data['Qty'], 
                color='#F44336', alpha=0.7, 
                label='売り板', edgecolor='#D32F2F', linewidth=1)
        
        # 数量ラベルを追加
        max_qty = ask_data['Qty'].max() if len(ask_data) > 0 else 0
        for idx, row in ask_data.iterrows():
            y_pos = price_to_index[row['Price']]
            ax.text(-row['Qty'] - max_qty * 0.01, y_pos, 
                    f"{row['Qty']:,.0f}", 
                    va='center', ha='right', fontsize=9)
    
    # Y軸の設定（すべての価格を表示）
    ax.set_yticks(np.arange(len(all_prices)))
    ax.set_yticklabels([f"{price:,.0f}円" for price in all_prices], fontsize=10)
    # Y軸を反転して、価格が高い方を上に表示
    ax.invert_yaxis()
    
    # X軸の設定
    ax.set_xlabel('数量（株）', fontsize=12, fontweight='bold')
    ax.set_ylabel('価格（円）', fontsize=12, fontweight='bold')
    
    # 銘柄名称を取得
    company_name = None
    try:
        from ..api.stocks_info import stocks_info
        si = stocks_info()
        company_name = si.get_company_name(code)
    except:
        pass
    # タイトルが取得できなかった場合は、銘柄コードをフォールバックとして使用
    if company_name is None:
        company_name = str(code)
    
    # タイトルの設定
    ax.set_title(f'板情報チャート - 銘柄コード: {str(company_name)} ({code})', 
                 fontsize=14, fontweight='bold', pad=20)
    
    # グリッドの設定
    ax.grid(True, alpha=0.3, linestyle='--', axis='x')
    ax.axvline(x=0, color='black', linewidth=1, linestyle='-')
    
    # 凡例の設定
    if len(bid_data) > 0 or len(ask_data) > 0:
        ax.legend(loc='upper right', fontsize=10, framealpha=0.9)
    
    # レイアウトの調整
    plt.tight_layout()
    
    # チャートを表示
    plt.show()
