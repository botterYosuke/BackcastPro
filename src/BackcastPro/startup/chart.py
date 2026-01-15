# -*- coding: utf-8 -*-
import datetime
import pandas as pd


def chart(code: str = "", from_: datetime = None, to: datetime = None,
            df: pd.DataFrame = None, title: str = None) -> pd.DataFrame | None:
    """
    株価データを指定して株価チャートを表示する
    
    Args:
        code: 銘柄コード（例: "6723"）
        from_: 開始日（datetime, オプション）
        to: 終了日（datetime, オプション）
        df: 株価データ（pandas DataFrame）
        title: チャートのタイトル（オプション）
    """
    if df is None:
        return chart_by_code(code, from_, to)

    return chart_by_df(df)


def chart_by_code(code: str, from_: datetime = None, to: datetime = None) -> pd.DataFrame:
    """
    銘柄コードを指定して株価チャートを表示する

    Args:
        code: 銘柄コード（例: "6723"）
        from_: 開始日（datetime, オプション）
        to: 終了日（datetime, オプション）

    Raises:
        NameError: get_stock_price関数が存在しない場合
        ValueError: データが空の場合、または必要なカラムが存在しない場合
    """

    # 株価データを取得
    from ..api.stocks_daily import stocks_price
    __sp__ = stocks_price()
    df = __sp__.get_japanese_stock_price_data(code, from_=from_, to=to)

    chart_by_df(df)

    return df

def _prepare_chart_df(df: pd.DataFrame) -> pd.DataFrame:
    """チャート表示用データを準備"""
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
    df['time'] = pd.to_datetime(df[date_col]).dt.strftime('%Y-%m-%d')
    
    # カラム名を小文字に統一
    df.columns = df.columns.str.lower()
    
    # 必要なカラムを抽出して数値変換
    df = df[['time', 'open', 'high', 'low', 'close', 'volume']].copy()
    df.iloc[:, 1:] = df.iloc[:, 1:].apply(pd.to_numeric, errors='coerce')
    return df.dropna()

def chart_by_df(df: pd.DataFrame) -> None:
    """株価データを指定して株価チャートを表示する"""
    code = df.iloc[0]['Code']
    
    # データを整形
    df = _prepare_chart_df(df)

    import json as json_module
    from IPython.display import HTML, display, DisplayObject
    
    # JSONデータを準備
    chart_data = {
        'data': df.to_dict('records'),
        'options': {'width': 600, 'height': 400},
        'title': code
    }

    class LightweightChartDisplay(DisplayObject):
        def _repr_mimebundle_(self, include=None, exclude=None):
            return {
                'application/vnd.lightweight-chart.v1+json': chart_data,
                'application/json': chart_data,
                'text/plain': json_module.dumps(chart_data, indent=2, ensure_ascii=False)
            }

    display(LightweightChartDisplay())
