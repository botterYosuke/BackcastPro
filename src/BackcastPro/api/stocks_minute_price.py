from .db_stocks_minute import db_stocks_minute
from trading_data.lib.util import _Timestamp

import pandas as pd
import threading
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class stocks_minute_price:
    """
    銘柄の1分足株価データを取得するためのクラス
    """

    def __init__(self):
        self.db = db_stocks_minute()

    def get_japanese_stock_minute_data(
        self, code="", from_: datetime = None, to: datetime = None
    ) -> pd.DataFrame:
        # 銘柄コードの検証
        if not code or not isinstance(code, str) or not code.strip():
            raise ValueError("銘柄コードが指定されていません")

        # from_/to の柔軟入力（str/date/pd.Timestamp）を正規化
        norm_from = _Timestamp(from_)
        norm_to = _Timestamp(to)

        if norm_from and norm_to and norm_from > norm_to:
            raise ValueError("開始日が終了日より後になっています")

        # DBファイルの準備（存在しなければクラウドからダウンロードを試行）
        self.db.ensure_db_ready(code)

        # cacheフォルダから取得
        df = self.db.load_stock_prices_from_cache(code, from_, to)
        if df is not None and not df.empty:
            return df

        raise ValueError(f"1分足データの取得に失敗しました: {code}")


def get_stock_minute(code, from_: datetime = None, to: datetime = None) -> pd.DataFrame:
    """
    1分足株価四本値

    - 1分足の株価データ（OHLCV + 売買代金）を取得します。
    - データの取得では、銘柄コード（code）の指定が必須となります。

    Args:
        code: 銘柄コード（例: "7203"）
        from_: 開始日（datetime, str, または None）
        to: 終了日（datetime, str, または None）

    Returns:
        DataFrame: 1分足株価データ（DatetimeIndexとして日時がインデックスに設定されている）
            カラム: Date, Time, Code, Open, High, Low, Close, Volume, Value
    """
    from .stocks_minute_price import stocks_minute_price
    __sp__ = stocks_minute_price()

    # 1分足株価データを取得
    df = __sp__.get_japanese_stock_minute_data(code=code, from_=from_, to=to)

    # DatetimeIndexであることを保証
    if df is not None and not df.empty:
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'Datetime' in df.columns:
                df = df.copy()
                df['Datetime'] = pd.to_datetime(df['Datetime'])
                df = df.set_index('Datetime')
            elif 'Date' in df.columns and 'Time' in df.columns:
                df = df.copy()
                df['Datetime'] = pd.to_datetime(
                    df['Date'].astype(str) + ' ' + df['Time'].astype(str)
                )
                df = df.set_index('Datetime')
            else:
                import warnings
                warnings.warn(
                    f"get_stock_minute('{code}') が返したDataFrameにDatetime列がなく、"
                    "インデックスもDatetimeIndexではありません。",
                    stacklevel=2
                )
        # 日時順にソート
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.sort_index()

    return df
