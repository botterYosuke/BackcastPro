from .db_manager import db_manager
import pandas as pd
import duckdb
import os
from typing import List, Tuple, Optional, Dict
from datetime import datetime
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class db_stocks_minute(db_manager):

    _db_subdir = "stocks_minute"

    # 1分足データの外部データソースパス（環境変数で上書き可能）
    _MINUTE_DATA_DIR_ENV = "STOCKDATA_MINUTE_DIR"
    _MINUTE_DATA_DIR_DEFAULT = r"S:\jp\stocks_minute"

    def __init__(self):
        super().__init__()
        # 1分足データ専用ディレクトリ（環境変数 > デフォルト > cache_dir/stocks_minute）
        self._minute_data_dir = os.environ.get(
            self._MINUTE_DATA_DIR_ENV,
            self._MINUTE_DATA_DIR_DEFAULT
        )

    def _get_db_path(self, code: str = None) -> str:
        """DBファイルパスを取得（1分足データ専用ディレクトリを優先）"""
        if code:
            # 1分足データ専用ディレクトリを優先チェック
            minute_path = os.path.join(self._minute_data_dir, f"{code}.duckdb")
            if os.path.exists(minute_path):
                return minute_path
        # フォールバック: 通常のcache_dir/stocks_minute
        return super()._get_db_path(code)


    def _ensure_metadata_table(self, db: duckdb.DuckDBPyConnection) -> None:
        """
        メタデータテーブルが存在することを確認し、なければ作成する
        """
        table_name = "stocks_minute_metadata"
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

        table_name = "stocks_minute_metadata"

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
        ファイルが銘柄コード単位のため、Codeの完全一致/前方一致の両方で検索する

        Returns:
            メタデータの辞書、存在しない場合はNone
        """
        table_name = "stocks_minute_metadata"

        if not self._table_exists(db, table_name):
            return None

        # 完全一致を試行
        result = db.execute(
            f'SELECT "Code", "from_date", "to_date", "record_count", "last_updated" FROM {table_name} WHERE "Code" = ?',
            [code]
        ).fetchone()

        # ファイルが銘柄コード単位のため、完全一致しない場合は先頭レコードを取得
        if not result:
            result = db.execute(
                f'SELECT "Code", "from_date", "to_date", "record_count", "last_updated" FROM {table_name} LIMIT 1'
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
        request_from = from_.date() if isinstance(from_, datetime) and not isinstance(from_, type(saved_from)) else (from_ if from_ else saved_from)
        request_to = to.date() if isinstance(to, datetime) and not isinstance(to, type(saved_to)) else (to if to else saved_to)

        # datetime.date に統一
        if hasattr(request_from, 'date') and callable(request_from.date):
            request_from = request_from.date()
        if hasattr(request_to, 'date') and callable(request_to.date):
            request_to = request_to.date()

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
        1分足株価時系列をDuckDBに保存（アップサート、動的テーブル作成対応）

        Args:
            code (str): 銘柄コード
            df (pd.DataFrame): カラム（Date, Time, Open, High, Low, Close, Volume, Value）
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
            required_columns = ['Date', 'Time', 'Open', 'High', 'Low', 'Close', 'Volume']

            # DatetimeIndexの場合はDateとTimeに分離
            if df.index.name == 'Datetime' or (isinstance(df.index, pd.DatetimeIndex) and df.index.name != 'Date'):
                df = df.copy()
                if 'Date' not in df.columns:
                    df['Date'] = df.index.date
                if 'Time' not in df.columns:
                    df['Time'] = df.index.strftime('%H:%M')
                df = df.reset_index(drop=True)
            elif df.index.name == 'Date' or isinstance(df.index, pd.DatetimeIndex):
                if 'Date' in df.columns:
                    df = df.reset_index(drop=True)
                else:
                    df = df.reset_index()

            # 必須カラムが存在するかチェック
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                logger.warning(f"必須カラムが不足しています: {missing_columns}。保存をスキップします。")
                return

            # 保存対象カラムを選択
            save_columns = ['Date', 'Time', 'Open', 'High', 'Low', 'Close', 'Volume']
            if 'Value' in df.columns:
                save_columns.append('Value')
            df_to_save = df[save_columns].copy()

            # Codeカラムを追加
            if 'Code' in df.columns:
                df_to_save['Code'] = df['Code'].iloc[0] if len(df) > 0 else code
            elif 'Code' not in df_to_save.columns:
                df_to_save['Code'] = code

            # 同一日時の重複データを事前にフィルタリング
            if 'Date' in df_to_save.columns and 'Time' in df_to_save.columns:
                df_to_save['Date'] = pd.to_datetime(df_to_save['Date'], errors='coerce')
                df_to_save = df_to_save.dropna(subset=['Date'])
                if not df_to_save.empty:
                    df_to_save = df_to_save.sort_values(by=['Date', 'Time'], kind='mergesort')
                    df_to_save = df_to_save.drop_duplicates(subset=['Code', 'Date', 'Time'], keep='last')

            with self.get_db(code) as db:

                table_name = "stocks_minute"

                db.execute("BEGIN TRANSACTION")

                try:

                    if self._table_exists(db, table_name):
                        logger.info(f"テーブル:{table_name} は、すでに存在しています。新規データをチェックします。")
                        existing_df = db.execute(
                            f'SELECT DISTINCT "Code", "Date", "Time" FROM {table_name}'
                        ).fetchdf()

                        if not existing_df.empty:
                            existing_df['Date'] = pd.to_datetime(existing_df['Date']).dt.strftime('%Y-%m-%d')
                            existing_df['Code'] = existing_df['Code'].astype(str)
                            existing_pairs = set(
                                [(str(row['Code']), str(row['Date']), str(row['Time'])) for _, row in existing_df.iterrows()]
                            )
                        else:
                            existing_pairs = set()

                        df_to_save_copy = df_to_save.copy()
                        if 'Date' in df_to_save_copy.columns:
                            df_to_save_copy['Date'] = pd.to_datetime(df_to_save_copy['Date']).dt.strftime('%Y-%m-%d')
                        if 'Code' in df_to_save_copy.columns:
                            df_to_save_copy['Code'] = df_to_save_copy['Code'].astype(str)

                        new_pairs = set(
                            [(str(row['Code']), str(row['Date']), str(row['Time'])) for _, row in df_to_save_copy.iterrows()]
                        )

                        unique_pairs = new_pairs - existing_pairs
                        if unique_pairs:
                            mask = df_to_save_copy.apply(
                                lambda row: (str(row['Code']), str(row['Date']), str(row['Time'])) in unique_pairs,
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
                            primary_keys = ['Date', 'Time', 'Code']
                            self._create_table_from_dataframe(db, table_name, df_to_save_normalized, primary_keys)
                            if 'Code' in df_to_save_normalized.columns:
                                db.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_Code ON {table_name}("Code")')
                            if 'Date' in df_to_save_normalized.columns:
                                db.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_Date ON {table_name}("Date")')
                            self._batch_insert_data(db, table_name, df_to_save_normalized)

                    # メタデータの保存
                    if 'Date' in df_to_save.columns:
                        date_stats = db.execute(
                            f'SELECT MIN("Date") as min_date, MAX("Date") as max_date, COUNT(*) as count FROM {table_name}'
                        ).fetchone()

                        if date_stats and date_stats[0]:
                            actual_from = str(date_stats[0])
                            actual_to = str(date_stats[1])
                            actual_count = date_stats[2]

                            meta_code = code
                            self._save_metadata(db, meta_code, actual_from, actual_to, actual_count)

                    db.execute("COMMIT")
                    logger.info(f"1分足priceデータをDuckDBに保存しました: 銘柄コード={code}, 件数={len(df_to_save)}")

                except Exception as e:
                    db.execute("ROLLBACK")
                    raise e

        except Exception as e:
            logger.error(f"キャッシュの保存に失敗しました: {str(e)}", exc_info=True)
            raise


    def load_stock_prices_from_cache(self, code: str, from_: datetime = None, to: datetime = None) -> pd.DataFrame:
        """
        1分足株価時系列をDuckDBから取得

        Args:
            code (str): 銘柄コード
            from_ (datetime, optional): 取得開始日
            to (datetime, optional): 取得終了日

        Returns:
            pd.DataFrame: 1分足株価データ（DatetimeIndex）
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

            table_name = "stocks_minute"

            with self.get_db(code) as db:

                if not self._table_exists(db, table_name):
                    logger.debug(f"キャッシュにデータがありません: {code}")
                    return pd.DataFrame()

                metadata = self._get_metadata(db, code)
                if metadata:
                    coverage = self._check_period_coverage(metadata, from_, to)

                    logger.info(f"期間チェック: {code} - {coverage['message']}")

                    if not coverage['is_covered']:
                        logger.warning(f"要求期間が保存済み期間外です: {code}\n")
                        return pd.DataFrame()
                else:
                    # メタデータがない場合でもデータ自体は取得を試みる
                    logger.info(f"メタデータが存在しません: {code}（データ取得を試みます）")

                params = []
                cond_parts = []
                if start_date:
                    cond_parts.append('"Date" >= ?')
                    params.append(start_date)
                if end_date:
                    cond_parts.append('"Date" <= ?')
                    params.append(end_date)

                where_clause = f"WHERE {' AND '.join(cond_parts)}" if cond_parts else ""
                query = f'SELECT "Date", "Time", "Open", "High", "Low", "Close", "Volume", "Value" FROM {table_name} {where_clause} ORDER BY "Date", "Time"'

                df = db.execute(query, params).fetchdf()

                # DateとTimeを結合してDatetimeIndexを作成
                if not df.empty and 'Date' in df.columns and 'Time' in df.columns:
                    df['Datetime'] = pd.to_datetime(
                        df['Date'].astype(str) + ' ' + df['Time'].astype(str)
                    )
                    df = df.drop(columns=['Date', 'Time'])
                    df = df.set_index('Datetime')
                    df = df.sort_index()

                logger.info(f"1分足株価データをDuckDBから読み込みました: {code} ({len(df)}件)")

                return df

        except Exception as e:
            logger.error(f"キャッシュの読み込みに失敗しました: {str(e)}", exc_info=True)
            return pd.DataFrame()
