from .db_manager import db_manager
import pandas as pd
import duckdb
import os
from typing import List, Tuple, Optional, Dict
from datetime import datetime
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class db_stocks_info(db_manager):

    def __init__(self):
        super().__init__()

    def save_listed_info(self, df: pd.DataFrame) -> None:
        """
        各上場銘柄の基本情報一覧をDuckDBに保存（アップサート、動的テーブル作成対応）

        Args:
            df (pd.DataFrame): J-Quantsのカラムを想定（Date, Code, CompanyName, CompanyNameEnglish, ...）
        """
        try:
            if not self.isEnable:
                return

            if df is None or df.empty:
                logger.info("上場銘柄情報が空のため保存をスキップしました")
                return

            # 必須カラムの定義
            required_columns = [
                'Date', 'Code', 'CompanyName', 'CompanyNameEnglish',
                'Sector17Code', 'Sector17CodeName',
                'Sector33Code', 'Sector33CodeName',
                'ScaleCategory', 'MarketCode', 'MarketCodeName'
            ]

            # 必須カラムが存在するかチェック
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                logger.warning(f"必須カラムが不足しています: {missing_columns}。保存をスキップします。")
                return
            
            # 必須カラムのみを選択
            df_to_save = df[required_columns].copy()
            
            # 日付形式を統一（YYYY-MM-DD）
            df_to_save['Date'] = pd.to_datetime(df_to_save['Date']).dt.strftime('%Y-%m-%d')
            df_to_save['Code'] = df_to_save['Code'].astype(str)

            # DataFrame 内の (Code, Date) の重複を除外
            df_to_save = df_to_save.drop_duplicates(subset=['Code', 'Date'], keep='first')
            logger.info(f"重複を除外後: {len(df_to_save)} 件")

            with self.get_db() as db:
                table_name = "listed_info"
                db.execute("BEGIN TRANSACTION")

                try:
                    if self._table_exists(db, table_name):
                        logger.info(f"テーブル:{table_name} は既に存在しています。新規データをチェックします。")
                        
                        existing_df = db.execute(
                            f'SELECT DISTINCT "Code", "Date" FROM {table_name}'
                        ).fetchdf()
                        
                        if not existing_df.empty:
                            existing_df['Date'] = pd.to_datetime(existing_df['Date']).dt.strftime('%Y-%m-%d')
                            existing_df['Code'] = existing_df['Code'].astype(str)
                            existing_pairs = set(
                                [(row['Code'], row['Date']) for _, row in existing_df.iterrows()]   
                            )                         
                        else:
                            existing_pairs = set()

                        new_pairs = set(
                            [(row['Code'], row['Date']) for _, row in df_to_save.iterrows()]
                        )                        
                        
                        unique_pairs = new_pairs - existing_pairs
                        
                        if unique_pairs:
                            mask = df_to_save.apply(
                                lambda row: (row['Code'], row['Date']) in unique_pairs,
                                axis=1
                            )
                            new_data_df = df_to_save[mask].copy()
                            logger.info(f"新規データ {len(new_data_df)} 件を追加します")
                            self._batch_insert_data(db, table_name, new_data_df)
                        else:
                            logger.info(f"新規データはありません")
                    
                    else:
                        if not self._table_exists(db, table_name):
                            logger.info(f"新しいテーブル {table_name} を作成します")
                            
                            primary_keys = ['Code', 'Date']
                            self._create_table_from_dataframe(db, table_name, df_to_save, primary_keys)
                            
                            db.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_code ON {table_name}("Code")')
                            db.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_date ON {table_name}("Date")')
                            db.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_sector17 ON {table_name}("Sector17Code")')
                            
                            self._batch_insert_data(db, table_name, df_to_save)
                            logger.info(f"データ {len(df_to_save)} 件を挿入しました")
                    
                    db.execute("COMMIT")
                    logger.info(f"上場銘柄情報をDuckDBに保存しました: 件数={len(df_to_save)}")
                
                except Exception as e:
                    db.execute("ROLLBACK")
                    raise e

        except Exception as e:
            logger.error(f"上場銘柄情報の保存に失敗しました: {str(e)}", exc_info=True)
            raise


    def load_listed_info_from_cache(self, code: str = "", date: str = "") -> pd.DataFrame:
        """
        上場銘柄情報をDuckDBから取得
        
        Args:
            code (str, optional): 銘柄コード（指定時はその銘柄のみ取得）
            date (str, optional): 日付（YYYY-MM-DD形式、指定時はその日付のデータのみ取得）
            
        Returns:
            pd.DataFrame: 上場銘柄情報データフレーム
        """
        try:
            if not self.isEnable:
                return pd.DataFrame()

            table_name = "listed_info"

            with self.get_db() as db:
                if not self._table_exists(db, table_name):
                    logger.debug(f"キャッシュにデータがありません（外部APIから取得します）")
                    return pd.DataFrame()

                params = []
                cond_parts = []
                
                if code:
                    cond_parts.append('"Code" = ?')
                    params.append(str(code))
                
                if date:
                    if isinstance(date, str):
                        date = pd.to_datetime(date).strftime('%Y-%m-%d')
                    cond_parts.append('"Date" = ?')
                    params.append(date)

                where_clause = f"WHERE {' AND '.join(cond_parts)}" if cond_parts else ""
                query = f'SELECT * FROM {table_name} {where_clause} ORDER BY "Date" DESC, "Code"'

                df = db.execute(query, params).fetchdf()

                if not df.empty:
                    logger.info(f"上場銘柄情報をDuckDBから読み込みました ({len(df)}件)")
                else:
                    logger.debug(f"キャッシュにデータがありません")

                return df

        except Exception as e:
            logger.error(f"キャッシュの読み込みに失敗しました: {str(e)}", exc_info=True)
            return pd.DataFrame()


    def ensure_db_ready(self) -> None:
        """
        DuckDBファイルの準備を行う（存在しなければFTPからダウンロードを試行）
        """
        if not self.isEnable:
            return

        db_path = os.path.join(self.cache_dir, "listed_info.duckdb")

        if not os.path.exists(db_path):
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            # FTPからダウンロードを試行
            if self._download_from_ftp(db_path):
                logger.info(f"DuckDBファイルをFTPからダウンロードしました: {db_path}")
            else:
                logger.debug(f"FTPにDuckDBファイルが存在しません: listed_info.duckdb")


    @contextmanager
    def get_db(self):
        """
        DuckDBデータベース接続を取得（コンテキストマネージャー対応）

        Yields:
            duckdb.DuckDBPyConnection: DuckDB接続オブジェクト
        """
        db_path = os.path.join(self.cache_dir, "listed_info.duckdb")
        if not os.path.exists(db_path):
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            # FTPからダウンロードを試行
            if self._download_from_ftp(db_path):
                logger.info(f"DuckDBファイルをFTPからダウンロードしました: {db_path}")
            else:
                logger.info(f"DuckDBファイルを作成しました: {db_path}")

        db = duckdb.connect(db_path)
        try:
            yield db
        finally:
            db.close()

    def _download_from_ftp(self, local_path: str) -> bool:
        """
        FTPサーバーからDuckDBファイルをダウンロード
        """
        import ftplib
        
        FTP_HOST = 'backcast.i234.me'
        FTP_USER = 'sasaco_worker'
        FTP_PASSWORD = 'S#1y9c%7o9'
        FTP_PORT = 21
        REMOTE_DIR = '/StockData/jp'
        
        try:
            with ftplib.FTP() as ftp:
                ftp.connect(FTP_HOST, FTP_PORT)
                ftp.login(FTP_USER, FTP_PASSWORD)
                
                remote_file = "listed_info.duckdb"
                
                # ファイルサイズ確認（存在確認も兼ねる）
                try:
                    ftp.voidcmd(f"TYPE I")
                    size = ftp.size(remote_file)
                    if size is None: # sizeコマンドがサポートされていない場合のフォールバックは省略
                        pass
                except Exception:
                    logger.debug(f"FTPサーバーにファイルが見つかりません: {remote_file}")
                    return False

                logger.info(f"FTPダウンロード開始: {remote_file} -> {local_path}")
                
                with open(local_path, 'wb') as f:
                    ftp.retrbinary(f"RETR {remote_file}", f.write)
                
                logger.info(f"FTPダウンロード完了: {local_path}")
                return True
                
        except Exception as e:
            logger.warning(f"FTPダウンロード失敗: {e}")
            # ダウンロード中の不完全なファイルが残っている場合は削除
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except:
                    pass
            return False
