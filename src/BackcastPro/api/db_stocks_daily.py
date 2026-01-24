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

class db_stocks_daily(db_manager):

    def __init__(self):
        super().__init__()


    def _ensure_metadata_table(self, db: duckdb.DuckDBPyConnection) -> None:
        """
        メタデータテーブルが存在することを確認し、なければ作成する
        """
        table_name = "stocks_daily_metadata"
        if not self._table_exists(db, table_name):
            create_sql = f"""
            CREATE TABLE {table_name} (
                "Code" VARCHAR(20) PRIMARY KEY,
                "from_date" DATE,
                "to_date" DATE,
                "record_count" INTEGER,
                "last_updated" TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
            db.execute(create_sql)
            logger.info(f"メタデータテーブル '{table_name}' を作成しました")


    def _save_metadata(self, db: duckdb.DuckDBPyConnection, code: str, from_date: str, to_date: str, record_count: int) -> None:
        """
        株価データの保存期間をメタデータテーブルに保存/更新
        
        Args:
            db: DuckDB接続
            code: 銘柄コード
            from_date: データ開始日 (YYYY-MM-DD形式)
            to_date: データ終了日 (YYYY-MM-DD形式)
            record_count: レコード数
        """
        self._ensure_metadata_table(db)
        
        table_name = "stocks_daily_metadata"
        
        # 既存のメタデータを取得
        existing = db.execute(
            f'SELECT "from_date", "to_date", "record_count" FROM {table_name} WHERE "Code" = ?',
            [code]
        ).fetchone()
        
        if existing:
            # 既存データがある場合は期間を拡張
            old_from, old_to, old_count = existing
            new_from = min(from_date, str(old_from)) if old_from else from_date
            new_to = max(to_date, str(old_to)) if old_to else to_date
            
            # 更新
            db.execute(
                f"""
                UPDATE {table_name}
                SET "from_date" = ?, "to_date" = ?, "record_count" = ?, "last_updated" = CURRENT_TIMESTAMP
                WHERE "Code" = ?
                """,
                [new_from, new_to, record_count, code]
            )
            logger.info(f"メタデータを更新しました: {code} ({new_from} ～ {new_to}, {record_count}件)")
        else:
            # 新規挿入
            db.execute(
                f"""
                INSERT INTO {table_name} ("Code", "from_date", "to_date", "record_count")
                VALUES (?, ?, ?, ?)
                """,
                [code, from_date, to_date, record_count]
            )
            logger.info(f"メタデータを作成しました: {code} ({from_date} ～ {to_date}, {record_count}件)")


    def _get_metadata(self, db: duckdb.DuckDBPyConnection, code: str) -> Optional[Dict]:
        """
        メタデータを取得
        
        Returns:
            メタデータの辞書、存在しない場合はNone
        """
        table_name = "stocks_daily_metadata"
        
        if not self._table_exists(db, table_name):
            return None
        
        result = db.execute(
            f'SELECT "Code", "from_date", "to_date", "record_count", "last_updated" FROM {table_name} WHERE "Code" = ?',
            [code]
        ).fetchone()
        
        if result:
            return {
                'code': result[0],
                'from_date': result[1],
                'to_date': result[2],
                'record_count': result[3],
                'last_updated': result[4]
            }
        return None


    def _check_period_coverage(self, metadata: Optional[Dict], from_: Optional[datetime], to: Optional[datetime]) -> Dict:
        """
        要求された期間が保存済み期間内かをチェック

        Args:
            metadata: メタデータ辞書
            from_: 要求開始日
            to: 要求終了日

        Returns:
            カバレッジ情報の辞書
        """
        if not metadata:
            return {
                'is_covered': False,
                'message': 'データが保存されていません',
                'saved_from': None,
                'saved_to': None
            }

        saved_from = metadata['from_date']
        saved_to = metadata['to_date']

        # 日付をdate型に変換
        if isinstance(saved_from, str):
            saved_from = datetime.strptime(saved_from, '%Y-%m-%d').date()
        if isinstance(saved_to, str):
            saved_to = datetime.strptime(saved_to, '%Y-%m-%d').date()

        # 要求された期間がない場合は全期間カバー済みと判定
        if from_ is None and to is None:
            return {
                'is_covered': True,
                'message': f'保存期間: {saved_from} ～ {saved_to}',
                'saved_from': saved_from,
                'saved_to': saved_to
            }

        # 要求された期間をチェック
        request_from = from_.date() if from_ else saved_from
        request_to = to.date() if to else saved_to

        # 要求期間が保存済み期間内にあるかチェック
        is_covered = (saved_from <= request_from) and (request_to <= saved_to)

        if is_covered:
            message = f'要求期間は保存済み ({saved_from} ～ {saved_to})'
        else:
            message = f'要求期間の一部または全部が未保存 (保存済み: {saved_from} ～ {saved_to}, 要求: {request_from} ～ {request_to})'

        return {
            'is_covered': is_covered,
            'message': message,
            'saved_from': saved_from,
            'saved_to': saved_to,
            'request_from': request_from,
            'request_to': request_to
        }


    def save_stock_prices(self, code: str, df: pd.DataFrame, from_: datetime = None, to: datetime = None) -> None:
        """
        株価時系列をDuckDBに保存（アップサート、動的テーブル作成対応）

        Args:
            code (str): 銘柄コード
            df (pd.DataFrame): J-Quantsのカラムを想定（Date, Open, High, Low, Close, Volume）
            from_ (datetime, optional): データ開始日（指定しない場合はdfから自動取得）
            to (datetime, optional): データ終了日（指定しない場合はdfから自動取得）
        """
        try:
            if not self.isEnable:
                return

            if df is None or df.empty:
                logger.info("priceデータが空のため保存をスキップしました")
                return

            # 必須カラムの定義
            required_columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            
            # Dateがインデックスになっている場合は、カラムとして追加
            # Dateがカラムとして既に存在する場合は、インデックスを削除（drop=True）
            if df.index.name == 'Date' or isinstance(df.index, pd.DatetimeIndex):
                if 'Date' in df.columns:
                    # Dateがカラムとして存在する場合は、インデックスを削除
                    df = df.reset_index(drop=True)
                else:
                    # Dateがカラムとして存在しない場合は、インデックスをカラムとして追加
                    df = df.reset_index()
            
            # 必須カラムが存在するかチェック
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                logger.warning(f"必須カラムが不足しています: {missing_columns}。保存をスキップします。")
                return
            
            # 必須カラムのみを選択（UpperLimit/LowerLimitなどの追加カラムを除外）
            df_to_save = df[required_columns].copy()
            
            # Codeカラムを追加（Codeカラムが存在する場合はリネーム、存在しない場合は追加）
            if 'Code' in df.columns:
                df_to_save['Code'] = df['Code'].iloc[0] if len(df) > 0 else code
            elif 'Code' not in df_to_save.columns:
                df_to_save['Code'] = code
            
            # 同一日付の重複データを事前にフィルタリング（最新のデータを保持）
            if 'Date' in df_to_save.columns:
                # Dateをdatetime型に変換
                df_to_save['Date'] = pd.to_datetime(df_to_save['Date'], errors='coerce')
                # 無効な日付を除外
                df_to_save = df_to_save.dropna(subset=['Date'])
                if not df_to_save.empty:
                    # 同一日付のデータがある場合、最新のデータを保持（keep='last'）
                    df_to_save = df_to_save.sort_values(by='Date', kind='mergesort')
                    df_to_save = df_to_save.drop_duplicates(subset=['Code', 'Date'], keep='last')

            with self.get_db(code) as db:

                # テーブル名
                table_name = "stocks_daily"

                # トランザクション開始
                db.execute("BEGIN TRANSACTION")

                try:

                    if self._table_exists(db, table_name):
                        logger.info(f"テーブル:{table_name} は、すでに存在しています。新規データをチェックします。")
                        # CodeとDateの組み合わせで重複チェック
                        existing_df = db.execute(
                            f'SELECT DISTINCT "Code", "Date" FROM {table_name}'
                        ).fetchdf()
                        
                        if not existing_df.empty:
                            existing_df['Date'] = pd.to_datetime(existing_df['Date']).dt.strftime('%Y-%m-%d')
                            existing_df['Code'] = existing_df['Code'].astype(str)
                            existing_pairs = set(
                                [(str(row['Code']), str(row['Date'])) for _, row in existing_df.iterrows()]
                            )
                        else:
                            existing_pairs = set()
                        
                        df_to_save_copy = df_to_save.copy()
                        if 'Date' in df_to_save_copy.columns:
                            df_to_save_copy['Date'] = pd.to_datetime(df_to_save_copy['Date']).dt.strftime('%Y-%m-%d')
                        if 'Code' in df_to_save_copy.columns:
                            df_to_save_copy['Code'] = df_to_save_copy['Code'].astype(str)
                        
                        new_pairs = set(
                            [(str(row['Code']), str(row['Date'])) for _, row in df_to_save_copy.iterrows()]
                        )
                        
                        unique_pairs = new_pairs - existing_pairs
                        if unique_pairs:
                            mask = df_to_save_copy.apply(
                                lambda row: (str(row['Code']), str(row['Date'])) in unique_pairs,
                                axis=1
                            )
                            new_data_df = df_to_save[mask].copy()
                            if 'Date' in new_data_df.columns:
                                new_data_df['Date'] = pd.to_datetime(new_data_df['Date']).dt.strftime('%Y-%m-%d')
                            if 'Code' in new_data_df.columns:
                                new_data_df['Code'] = new_data_df['Code'].astype(str)
                            logger.info(f"新規データ {len(new_data_df)} 件を追加します（銘柄コード: {code}）")
                            self._batch_insert_data(db, table_name, new_data_df)
                        else:
                            logger.info(f"新規データはありません（銘柄コード: {code}）")

                    else:
                        if not self._table_exists(db, table_name):
                            logger.info(f"新しいテーブル {table_name} を作成します")
                            df_to_save_normalized = df_to_save.copy()
                            if 'Date' in df_to_save_normalized.columns:
                                df_to_save_normalized['Date'] = pd.to_datetime(df_to_save_normalized['Date']).dt.strftime('%Y-%m-%d')
                            primary_keys = ['Code', 'Date'] if 'Code' in df_to_save_normalized.columns and 'Date' in df_to_save_normalized.columns else ['Date']
                            self._create_table_from_dataframe(db, table_name, df_to_save_normalized, primary_keys)
                            if 'Code' in df_to_save_normalized.columns:
                                db.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_Code ON {table_name}("Code")')
                            if 'Date' in df_to_save_normalized.columns:
                                db.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_Date ON {table_name}("Date")')
                            self._batch_insert_data(db, table_name, df_to_save_normalized)

                    # メタデータの保存
                    if 'Date' in df_to_save.columns:
                        date_stats = db.execute(
                            f'SELECT MIN("Date") as min_date, MAX("Date") as max_date, COUNT(*) as count FROM {table_name} WHERE "Code" = ?',
                            [code]
                        ).fetchone()
                        
                        if date_stats and date_stats[0]:
                            actual_from = str(date_stats[0])
                            actual_to = str(date_stats[1])
                            actual_count = date_stats[2]
                            
                            self._save_metadata(db, code, actual_from, actual_to, actual_count)
                    
                    # トランザクションコミット
                    db.execute("COMMIT")
                    logger.info(f"priceデータをDuckDBに保存しました: 銘柄コード={code}, 件数={len(df_to_save)}")
                
                except Exception as e:
                    db.execute("ROLLBACK")
                    raise e

        except Exception as e:
            logger.error(f"キャッシュの保存に失敗しました: {str(e)}", exc_info=True)
            raise


    def load_stock_prices_from_cache(self, code: str, from_: datetime = None, to: datetime = None) -> pd.DataFrame:
        """
        株価時系列をDuckDBから取得
        
        Args:
            code (str): 銘柄コード
            from_ (datetime, optional): 取得開始日
            to (datetime, optional): 取得終了日
            
        Returns:
            pd.DataFrame: 株価データ
        """
        try:
            if not self.isEnable:
                return pd.DataFrame()

            start_date = ""
            end_date = ""
            if not from_ is None:
                if isinstance(from_, str):
                    from_ = datetime.strptime(from_, '%Y-%m-%d')
                start_date = from_.strftime('%Y-%m-%d')
            if not to is None:
                if isinstance(to, str):
                    to = datetime.strptime(to, '%Y-%m-%d')
                end_date = to.strftime('%Y-%m-%d')

            table_name = "stocks_daily"

            with self.get_db(code) as db:

                if not self._table_exists(db, table_name):
                    logger.debug(f"キャッシュにデータがありません（外部APIから取得します）: {code}")
                    return pd.DataFrame()

                metadata = self._get_metadata(db, code)
                if metadata:
                    coverage = self._check_period_coverage(metadata, from_, to)
                    
                    logger.info(f"期間チェック: {code} - {coverage['message']}")
                    
                    if not coverage['is_covered']:
                        logger.warning(f"要求期間が保存済み期間外です: {code}\n")
                        return pd.DataFrame()
                else:
                    logger.info(f"メタデータが存在しません: {code}")
                    return pd.DataFrame()

                params = []
                cond_parts = []
                cond_parts.append('"Code" = ?')
                params.append(code)
                if start_date:
                    cond_parts.append('"Date" >= ?')
                    params.append(start_date)
                if end_date:
                    cond_parts.append('"Date" <= ?')
                    params.append(end_date)

                where_clause = f"WHERE {' AND '.join(cond_parts)}" if cond_parts else ""
                query = f'SELECT * FROM {table_name} {where_clause} ORDER BY "Date"'

                df = db.execute(query, params).fetchdf()

                # Date列をDatetimeIndexに設定
                if not df.empty and 'Date' in df.columns:
                    df['Date'] = pd.to_datetime(df['Date'])
                    df = df.set_index('Date')

                logger.info(f"株価データをDuckDBから読み込みました: {code} ({len(df)}件)")

                return df

        except Exception as e:
            logger.error(f"キャッシュの読み込みに失敗しました: {str(e)}", exc_info=True)
            return pd.DataFrame()


    def ensure_db_ready(self, code: str) -> None:
        """
        DuckDBファイルの準備を行う（存在しなければFTPからダウンロードを試行）

        Args:
            code (str): 銘柄コード
        """
        if not self.isEnable:
            return

        # コードの正規化（サフィックス除去）
        normalized_code = code
        if len(code) > 4:
            normalized_code = code[:-1]

        db_path = os.path.join(self.cache_dir, "stocks_daily", f"{normalized_code}.duckdb")

        if not os.path.exists(db_path):
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            # FTPからダウンロードを試行
            if self._download_from_ftp(normalized_code, db_path):
                logger.info(f"DuckDBファイルをFTPからダウンロードしました: {db_path}")
            else:
                logger.debug(f"FTPにDuckDBファイルが存在しません: {normalized_code}")


    @contextmanager
    def get_db(self, code: str):
        """
        DuckDBデータベース接続を取得
        
        Args:
            code (str): 銘柄コード
        
        Yields:
            duckdb.DuckDBPyConnection: DuckDB接続オブジェクト
        """
        db_path = os.path.join(self.cache_dir, "stocks_daily", f"{code}.duckdb")
        if not os.path.exists(db_path):
            if len(code) > 4:
                code_retry = code[:-1]
                # 再帰呼び出しの結果を返す（ジェネレータなので yield from）
                yield from self.get_db(code_retry)
                return

            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            
            # FTPからダウンロードを試行
            if self._download_from_ftp(code, db_path):
                logger.info(f"DuckDBファイルをFTPからダウンロードしました: {db_path}")
            else:
                logger.info(f"DuckDBファイルを作成しました: {db_path}")

        db = duckdb.connect(db_path)
        try:
            yield db
        finally:
            db.close()

    def _download_from_ftp(self, code: str, local_path: str) -> bool:
        """
        FTPサーバーからDuckDBファイルをダウンロード
        """
        import ftplib
        
        FTP_HOST = 'backcast.i234.me'
        FTP_USER = 'sasaco_worker'
        FTP_PASSWORD = 'S#1y9c%7o9'
        FTP_PORT = 21
        REMOTE_DIR = '/StockData/jp/stocks_daily'
        
        try:
            with ftplib.FTP() as ftp:
                ftp.connect(FTP_HOST, FTP_PORT)
                ftp.login(FTP_USER, FTP_PASSWORD)
                
                remote_file = f"{REMOTE_DIR}/{code}.duckdb"
                
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
