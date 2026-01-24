from .lib.jquants import jquants
from .lib.e_api import e_api
from .lib.kabusap import kabusap
from .lib.stooq import stooq_daily_quotes
from .db_stocks_daily import db_stocks_daily
from .lib.util import _Timestamp

import pandas as pd
import threading
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class stocks_price:
    """
    銘柄の株価データを取得するためのクラス
    """

    def __init__(self):
        self.db = db_stocks_daily()

    def get_japanese_stock_price_data(
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

        # DBファイルの準備（存在しなければFTPからダウンロードを試行）
        self.db.ensure_db_ready(code)

        # 1) cacheフォルダから取得
        df = self.db.load_stock_prices_from_cache(code, norm_from, norm_to)
        if df is not None and not df.empty:
            return df

        # 2) 立花証券 e-支店から取得
        if not hasattr(self, "e_shiten"):
            self.e_shiten = e_api()
        if self.e_shiten.isEnable:
            df = self.e_shiten.get_daily_quotes(code=code, from_=norm_from, to=norm_to)
            if df is not None and not df.empty:
                # DataFrameをcacheフォルダに保存
                ## 非同期、遅延を避けるためデーモンスレッドで実行
                threading.Thread(
                    target=self.db.save_stock_prices, args=(code, df), daemon=True
                ).start()
                return df

        # 3) J-Quantsから取得
        if not hasattr(self, "jq"):
            self.jq = jquants()
        if self.jq.isEnable:
            df = self.jq.get_daily_quotes(code=code, from_=norm_from, to=norm_to)
            if df is not None and not df.empty:
                # DataFrameをcacheフォルダに保存
                ## 非同期、遅延を避けるためデーモンスレッドで実行
                threading.Thread(
                    target=self.db.save_stock_prices, args=(code, df), daemon=True
                ).start()
                return df

        # 4) stooqから取得
        df = stooq_daily_quotes(code=code, from_=norm_from, to=norm_to)
        if df is not None and not df.empty:
            # DataFrameをcacheフォルダに保存
            ## 非同期、遅延を避けるためデーモンスレッドで実行
            threading.Thread(
                target=self.db.save_stock_prices, args=(code, df), daemon=True
            ).start()
            return df

        raise ValueError(f"日本株式銘柄の取得に失敗しました: {code}")


def get_stock_daily(code, from_: datetime = None, to: datetime = None) -> pd.DataFrame:
    """
    株価四本値（/prices/daily_quotes）

    - 株価は分割・併合を考慮した調整済み株価（小数点第２位四捨五入）と調整前の株価を取得することができます。
    - データの取得では、銘柄コード（code）または日付（date）の指定が必須となります。

    Args:
        code: 銘柄コード（例: "7203.JP"）
        from_: 開始日（datetime, str, または None）
        to: 終了日（datetime, str, または None）

    Returns:
        DataFrame: 株価データ（DatetimeIndexとして日付がインデックスに設定されている）
    """
    from .stocks_price import stocks_price
    __sp__ = stocks_price()

    # 株価データを取得（内部で自動的にデータベースに保存される）
    df = __sp__.get_japanese_stock_price_data(code=code, from_=from_, to=to)

    # DatetimeIndexであることを保証
    if df is not None and not df.empty:
        if not isinstance(df.index, pd.DatetimeIndex):
            # Date列がある場合はそれをインデックスに設定
            if 'Date' in df.columns:
                df = df.copy()
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.set_index('Date')
            elif 'date' in df.columns:
                df = df.copy()
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')
                df.index.name = 'Date'
            else:
                import warnings
                warnings.warn(
                    f"get_stock_daily('{code}') が返したDataFrameにDate列がなく、"
                    "インデックスもDatetimeIndexではありません。",
                    stacklevel=2
                )
        # 日付順にソート
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.sort_index()

    return df