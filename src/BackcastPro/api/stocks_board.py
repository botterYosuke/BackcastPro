from .lib.jquants import jquants
from .lib.e_api import e_api
from .lib.kabusap import kabusap
from .lib.stooq import stooq_daily_quotes
from .db_stocks_daily import db_stocks_daily
from .db_stocks_board import db_stocks_board
import pandas as pd
import threading
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class stocks_board:
    """
    銘柄の板情報を取得するためのクラス
    """

    def __init__(self):
        self.db = db_stocks_board()


    def get_japanese_stock_board_data(self, code = "") -> pd.DataFrame:

        # 銘柄コードの検証
        if not code or not isinstance(code, str) or not code.strip():
            raise ValueError("銘柄コードが指定されていません")

        # 1) cacheフォルダから取得
        df = self.db.load_stock_board_from_cache(code)
        if df is not None and not df.empty:
            return df

        # 2) kabuステーションから取得
        if not hasattr(self, 'kabusap'):
            self.kabusap = kabusap()
        if self.kabusap.isEnable:
            df = self.kabusap.get_board(code=code)
            if df is not None and not df.empty:
                # DataFrameをDuckDBに保存
                ## 非同期、遅延を避けるためデーモンスレッドで実行
                threading.Thread(
                    target=self.db.save_stock_board, args=(code, df), daemon=True
                ).start()
                return df

        # 3) 立花証券 e-支店から取得
        if not hasattr(self, 'e_shiten'):
            self.e_shiten = e_api()
        if self.e_shiten.isEnable:
            df = self.e_shiten.get_board(code=code)
            if df is not None and not df.empty:
                # DataFrameをDuckDBに保存
                ## 非同期、遅延を避けるためデーモンスレッドで実行
                threading.Thread(
                    target=self.db.save_stock_board, args=(code, df), daemon=True
                ).start()
                return df

        raise ValueError(f"板情報の取得に失敗しました: {code}")


def get_stock_board(code) -> pd.DataFrame:
    """
    板情報を取得する
    """
    from .stocks_board import stocks_board
    __sb__ = stocks_board()

    return __sb__.get_japanese_stock_board_data(code=code)