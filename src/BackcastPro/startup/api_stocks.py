# -*- coding: utf-8 -*-
"""
Backtest自動初期化スクリプト

このスクリプトはIPythonカーネル起動時に自動実行され、
変数 `bt` を初期化し、`get_stock_price` 関数を利用可能にします。

注意: BackcastProは requirements.txt に記載されたパッケージを使用します。
"""

import sys
from datetime import datetime
import pandas as pd

    
def get_stock_price(code, from_: datetime = None, to: datetime = None) -> pd.DataFrame:
    """
    株価四本値（/prices/daily_quotes）

    - 株価は分割・併合を考慮した調整済み株価（小数点第２位四捨五入）と調整前の株価を取得することができます。
    - データの取得では、銘柄コード（code）または日付（date）の指定が必須となります。
    
    Args:
        code: 銘柄コード（例: "7203.JP"）
        from_: 開始日（datetime, str, または None）
        to: 終了日（datetime, str, または None）
    
    Returns:
        DataFrame: 株価データ（Date列がindexとして設定されている）
    """
    from ..api.stocks_daily import stocks_price
    __sp__ = stocks_price()

    # 株価データを取得（内部で自動的にデータベースに保存される）
    df = __sp__.get_japanese_stock_price_data(code=code, from_=from_, to=to)
    
    # Date列が存在する場合、indexとして設定する（Backtestで使用するため）
    if df is not None and not df.empty:
        if 'Date' in df.columns:
            # Date列をdatetime型に変換してindexに設定
            df = df.copy()  # 元のDataFrameを変更しないようにコピー
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
            # indexをソート（Backtestで必要）
            df.sort_index(inplace=True)
        elif not isinstance(df.index, pd.DatetimeIndex):
            # Date列がなく、indexもDatetimeIndexでない場合の警告
            import warnings
            warnings.warn(
                f"get_stock_price('{code}') が返したDataFrameに'Date'列がありません。"
                "Backtestで使用するには、Date列が必要です。",
                stacklevel=2
            )
    
    return df

def get_stock_board(code) -> pd.DataFrame:
    """
    板情報を取得する
    """
    from ..api.stocks_board import stocks_board
    __sb__ = stocks_board()

    return __sb__.get_japanese_stock_board_data(code=code)

def get_stock_info(code="", date: datetime = None) -> pd.DataFrame:
    """
    銘柄の情報を取得する
    """
    from ..api.stocks_info import stocks_info
    __si__ = stocks_info()    

    return __si__.get_japanese_listed_info(code=code, date=date)
