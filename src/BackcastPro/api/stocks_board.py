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


    def get_japanese_stock_board_data(self, code = "", date: datetime = None) -> pd.DataFrame:

        # 銘柄コードの検証
        if not code or not isinstance(code, str) or not code.strip():
            raise ValueError("銘柄コードが指定されていません")

        # DBファイルの準備（存在しなければクラウドからダウンロードを試行）
        self.db.ensure_db_ready(code)

        # 時間が指定されている場合、指定時刻の板情報を取得
        if date is not None:
            df = self.db.load_stock_board_from_cache(code, date)
            if df is not None and not df.empty:
                return df
            # 時間に指定がある場合、取得できなければエラー
            raise ValueError(f"{date}: 板情報の取得に失敗しました: {code}")

        # cacheフォルダから取得
        df = self.db.load_stock_board_from_cache(code, date)
        if df.empty:
            # 空のDataFrameの場合は次のデータソースを試す
            pass
        else:
            return df

        raise ValueError(f"板情報の取得に失敗しました: {code}")


def get_stock_board(code, date: datetime = None) -> pd.DataFrame:
    """
    板情報を取得する
    """
    from .stocks_board import stocks_board
    __sb__ = stocks_board()

    return __sb__.get_japanese_stock_board_data(code=code, date=date)