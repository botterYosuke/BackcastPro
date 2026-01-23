from .lib.jquants import jquants
from .db_stocks_info import db_stocks_info
import sys
import pandas as pd
import threading
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class stocks_info:
    """
    銘柄のデータを取得するためのクラス
    """

    def __init__(self):
        self.db = db_stocks_info()
        self.jq = jquants()

    def get_japanese_listed_info(self, code = "", date: datetime = None) -> pd.DataFrame:

        # DBファイルの準備（存在しなければFTPからダウンロードを試行）
        self.db.ensure_db_ready()

        # 1) J-Quantsから取得
        if self.jq.isEnable:
            df = self.jq.get_listed_info(code=code, date=date)
            # Codeをが4文字にする
            df['Code'] = df['Code'].str[:4]
            if df is not None and not df.empty:
                # DataFrameをcacheフォルダに保存
                ## 非同期、遅延を避けるためデーモンスレッドで実行
                threading.Thread(target=self.db.save_listed_info, args=(df,), daemon=True).start()
                return df

        # 2) cacheフォルダから取得
        df = self.db.load_listed_info_from_cache(code, date)
        if df.empty:
            # 空のDataFrameの場合は次のデータソースを試す
            pass
        else:
            return df

        raise ValueError(f"日本株式上場銘柄一覧の取得に失敗しました: {self.jq.isEnable}")

    def get_company_name(self, code: str):
        """
        銘柄コードを指定して銘柄名称を取得する
        """
        if not self.jq.isEnable:
            return str(code)
        
        title = None
        try:           
            # 銘柄コードを正規化（4桁の場合はそのまま、5桁の場合はそのまま）
            code_for_lookup = str(code).strip()
            # .JPなどのサフィックスを除去
            if '.' in code_for_lookup:
                code_for_lookup = code_for_lookup.split('.')[0]
            
            # 銘柄情報を取得
            df_info = self.jq.get_listed_info(code=code_for_lookup)
            
            # 銘柄名称を取得（CompanyNameカラムから）
            if not df_info.empty and 'CompanyName' in df_info.columns:
                company_name = df_info.iloc[0]['CompanyName']
                if pd.notna(company_name) and company_name:
                    title = str(company_name)
        except Exception as e:
            # エラーが発生してもチャートの表示は継続（タイトルなしで表示）
            print(f"警告: 銘柄名称の取得に失敗しました: {e}", file=sys.stderr)
            
        # タイトルが取得できなかった場合は、銘柄コードをフォールバックとして使用
        if title is None:
            title = str(code)

        return title


def get_stock_info(code="", date: datetime = None) -> pd.DataFrame:
    """
    銘柄の情報を取得する
    """
    from .stocks_info import stocks_info
    __si__ = stocks_info()    

    return __si__.get_japanese_listed_info(code=code, date=date)
