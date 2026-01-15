from .lib.jquants import jquants
from .lib.e_api import e_api
from .lib.kabusap import kabusap
from .lib.stooq import stooq_daily_quotes
from .db_stocks_daily import db_stocks_daily
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
        pass


    def get_japanese_stock_board_data(self, code = "") -> pd.DataFrame:

        # 銘柄コードの検証
        if not code or not isinstance(code, str) or not code.strip():
            raise ValueError("銘柄コードが指定されていません")

        # 1) kabuステーションから取得
        if not hasattr(self, 'kabusap'):
            self.kabusap = kabusap()
        if self.kabusap.isEnable:
            df = self.kabusap.get_board(code=code)
            if df is not None and not df.empty:
                return df

        # 2) 立花証券 e-支店から取得
        if not hasattr(self, 'e_shiten'):
            self.e_shiten = e_api()
        if self.e_shiten.isEnable:
            df = self.e_shiten.get_board(code=code)
            if df is not None and not df.empty:
                return df

        raise ValueError(f"板情報の取得に失敗しました: {code}")
