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
