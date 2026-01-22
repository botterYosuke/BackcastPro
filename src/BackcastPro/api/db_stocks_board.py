from .db_manager import db_manager
import pandas as pd
import duckdb
import os
from typing import Optional, Dict
from datetime import datetime
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class db_stocks_board(db_manager):

    def __init__(self):
        super().__init__()


    def _ensure_metadata_table(self, db: duckdb.DuckDBPyConnection) -> None:
        """
        メタデータテーブルが存在することを確認し、なければ作成する
        """
        table_name = "stocks_board_metadata"
        if not self._table_exists(db, table_name):
            create_sql = f"""
            CREATE TABLE {table_name} (
                "Code" VARCHAR(20) PRIMARY KEY,
                "from_timestamp" TIMESTAMP,
                "to_timestamp" TIMESTAMP,
                "record_count" INTEGER,
                "last_updated" TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
            db.execute(create_sql)
            logger.info(f"メタデータテーブル '{table_name}' を作成しました")


    def _save_metadata(self, db: duckdb.DuckDBPyConnection, code: str, from_timestamp: str, to_timestamp: str, record_count: int) -> None:
        """
        板情報の保存期間をメタデータテーブルに保存/更新

        Args:
            db: DuckDB接続
            code: 銘柄コード
            from_timestamp: データ開始時刻 (YYYY-MM-DD HH:MM:SS形式)
            to_timestamp: データ終了時刻 (YYYY-MM-DD HH:MM:SS形式)
            record_count: レコード数
        """
        self._ensure_metadata_table(db)

        table_name = "stocks_board_metadata"

        # 既存のメタデータを取得
        existing = db.execute(
            f'SELECT "from_timestamp", "to_timestamp", "record_count" FROM {table_name} WHERE "Code" = ?',
            [code]
        ).fetchone()

        if existing:
            # 既存データがある場合は期間を拡張
            old_from, old_to, old_count = existing
            new_from = min(from_timestamp, str(old_from)) if old_from else from_timestamp
            new_to = max(to_timestamp, str(old_to)) if old_to else to_timestamp

            # 更新
            db.execute(
                f"""
                UPDATE {table_name}
                SET "from_timestamp" = ?, "to_timestamp" = ?, "record_count" = ?, "last_updated" = CURRENT_TIMESTAMP
                WHERE "Code" = ?
                """,
                [new_from, new_to, record_count, code]
            )
            logger.info(f"メタデータを更新しました: {code} ({new_from} ～ {new_to}, {record_count}件)")
        else:
            # 新規挿入
            db.execute(
                f"""
                INSERT INTO {table_name} ("Code", "from_timestamp", "to_timestamp", "record_count")
                VALUES (?, ?, ?, ?)
                """,
                [code, from_timestamp, to_timestamp, record_count]
            )
            logger.info(f"メタデータを作成しました: {code} ({from_timestamp} ～ {to_timestamp}, {record_count}件)")


    def _get_metadata(self, db: duckdb.DuckDBPyConnection, code: str) -> Optional[Dict]:
        """
        メタデータを取得

        Returns:
            メタデータの辞書、存在しない場合はNone
        """
        table_name = "stocks_board_metadata"

        if not self._table_exists(db, table_name):
            return None

        result = db.execute(
            f'SELECT "Code", "from_timestamp", "to_timestamp", "record_count", "last_updated" FROM {table_name} WHERE "Code" = ?',
            [code]
        ).fetchone()

        if result:
            return {
                'code': result[0],
                'from_timestamp': result[1],
                'to_timestamp': result[2],
                'record_count': result[3],
                'last_updated': result[4]
            }
        return None


    def save_stock_board(self, code: str, df: pd.DataFrame) -> None:
        """
        板情報をDuckDBに保存（アップサート、動的テーブル作成対応）

        Args:
            code (str): 銘柄コード
            df (pd.DataFrame): 板情報のDataFrame（Timestamp列を含む）
        """
        try:
            if not self.isEnable:
                return

            if df is None or df.empty:
                logger.info("板情報データが空のため保存をスキップしました")
                return

            # Timestampカラムの確認と処理
            if 'Timestamp' not in df.columns:
                # Timestampカラムがない場合は現在時刻を追加
                df = df.copy()
                df['Timestamp'] = datetime.now()
                logger.info("Timestampカラムを追加しました")

            # Timestampがインデックスになっている場合はカラムとして追加
            if df.index.name == 'Timestamp' or isinstance(df.index, pd.DatetimeIndex):
                if 'Timestamp' not in df.columns:
                    df = df.reset_index()
                else:
                    df = df.reset_index(drop=True)

            # Codeカラムを追加（存在しない場合）
            if 'Code' not in df.columns:
                df['Code'] = code

            # Timestampをdatetime型に変換
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
            # 無効な日時を除外
            df = df.dropna(subset=['Timestamp'])

            if df.empty:
                logger.warning("有効なTimestampがないため保存をスキップしました")
                return

            # 同一タイムスタンプの重複データを事前にフィルタリング（最新のデータを保持）
            df = df.sort_values(by='Timestamp', kind='mergesort')
            df = df.drop_duplicates(subset=['Code', 'Timestamp'], keep='last')

            with self.get_db(code) as db:

                # テーブル名
                table_name = "stocks_board"

                # トランザクション開始
                db.execute("BEGIN TRANSACTION")

                try:

                    if self._table_exists(db, table_name):
                        logger.info(f"テーブル:{table_name} は、すでに存在しています。新規データをチェックします。")
                        # CodeとTimestampの組み合わせで重複チェック
                        existing_df = db.execute(
                            f'SELECT DISTINCT "Code", "Timestamp" FROM {table_name}'
                        ).fetchdf()

                        if not existing_df.empty:
                            existing_df['Timestamp'] = pd.to_datetime(existing_df['Timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
                            existing_df['Code'] = existing_df['Code'].astype(str)
                            existing_pairs = set(
                                [(str(row['Code']), str(row['Timestamp'])) for _, row in existing_df.iterrows()]
                            )
                        else:
                            existing_pairs = set()

                        df_to_save_copy = df.copy()
                        df_to_save_copy['Timestamp'] = pd.to_datetime(df_to_save_copy['Timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
                        df_to_save_copy['Code'] = df_to_save_copy['Code'].astype(str)

                        new_pairs = set(
                            [(str(row['Code']), str(row['Timestamp'])) for _, row in df_to_save_copy.iterrows()]
                        )

                        unique_pairs = new_pairs - existing_pairs
                        if unique_pairs:
                            mask = df_to_save_copy.apply(
                                lambda row: (str(row['Code']), str(row['Timestamp'])) in unique_pairs,
                                axis=1
                            )
                            new_data_df = df[mask].copy()
                            new_data_df['Timestamp'] = pd.to_datetime(new_data_df['Timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
                            new_data_df['Code'] = new_data_df['Code'].astype(str)
                            logger.info(f"新規データ {len(new_data_df)} 件を追加します（銘柄コード: {code}）")
                            self._batch_insert_data(db, table_name, new_data_df)
                        else:
                            logger.info(f"新規データはありません（銘柄コード: {code}）")

                    else:
                        logger.info(f"新しいテーブル {table_name} を作成します")
                        df_normalized = df.copy()
                        df_normalized['Timestamp'] = pd.to_datetime(df_normalized['Timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
                        primary_keys = ['Code', 'Timestamp']
                        self._create_table_from_dataframe(db, table_name, df_normalized, primary_keys)
                        db.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_Code ON {table_name}("Code")')
                        db.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_Timestamp ON {table_name}("Timestamp")')
                        self._batch_insert_data(db, table_name, df_normalized)

                    # メタデータの保存
                    timestamp_stats = db.execute(
                        f'SELECT MIN("Timestamp") as min_ts, MAX("Timestamp") as max_ts, COUNT(*) as count FROM {table_name} WHERE "Code" = ?',
                        [code]
                    ).fetchone()

                    if timestamp_stats and timestamp_stats[0]:
                        actual_from = str(timestamp_stats[0])
                        actual_to = str(timestamp_stats[1])
                        actual_count = timestamp_stats[2]

                        self._save_metadata(db, code, actual_from, actual_to, actual_count)

                    # トランザクションコミット
                    db.execute("COMMIT")
                    logger.info(f"板情報をDuckDBに保存しました: 銘柄コード={code}, 件数={len(df)}")

                except Exception as e:
                    db.execute("ROLLBACK")
                    raise e

        except Exception as e:
            logger.error(f"板情報の保存に失敗しました: {str(e)}", exc_info=True)
            raise


    def load_stock_board_from_cache(self, code: str, from_: datetime = None, to: datetime = None) -> pd.DataFrame:
        """
        板情報をDuckDBから取得

        Args:
            code (str): 銘柄コード
            from_ (datetime, optional): 取得開始時刻
            to (datetime, optional): 取得終了時刻

        Returns:
            pd.DataFrame: 板情報データ
        """
        try:
            if not self.isEnable:
                return pd.DataFrame()

            start_timestamp = ""
            end_timestamp = ""
            if from_ is not None:
                if isinstance(from_, str):
                    from_ = datetime.strptime(from_, '%Y-%m-%d %H:%M:%S')
                start_timestamp = from_.strftime('%Y-%m-%d %H:%M:%S')
            if to is not None:
                if isinstance(to, str):
                    to = datetime.strptime(to, '%Y-%m-%d %H:%M:%S')
                end_timestamp = to.strftime('%Y-%m-%d %H:%M:%S')

            table_name = "stocks_board"

            with self.get_db(code) as db:

                if not self._table_exists(db, table_name):
                    logger.debug(f"キャッシュに板情報がありません（外部APIから取得します）: {code}")
                    return pd.DataFrame()

                metadata = self._get_metadata(db, code)
                if metadata:
                    logger.info(f"板情報メタデータ: {code} - {metadata['from_timestamp']} ～ {metadata['to_timestamp']}, {metadata['record_count']}件")
                else:
                    logger.info(f"板情報メタデータが存在しません: {code}")

                params = []
                cond_parts = []
                cond_parts.append('"Code" = ?')
                params.append(code)
                if start_timestamp:
                    cond_parts.append('"Timestamp" >= ?')
                    params.append(start_timestamp)
                if end_timestamp:
                    cond_parts.append('"Timestamp" <= ?')
                    params.append(end_timestamp)

                where_clause = f"WHERE {' AND '.join(cond_parts)}" if cond_parts else ""
                query = f'SELECT * FROM {table_name} {where_clause} ORDER BY "Timestamp"'

                df = db.execute(query, params).fetchdf()

                logger.info(f"板情報をDuckDBから読み込みました: {code} ({len(df)}件)")

                return df

        except Exception as e:
            logger.error(f"板情報の読み込みに失敗しました: {str(e)}", exc_info=True)
            return pd.DataFrame()


    @contextmanager
    def get_db(self, code: str):
        """
        DuckDBデータベース接続を取得

        Args:
            code (str): 銘柄コード

        Yields:
            duckdb.DuckDBPyConnection: DuckDB接続オブジェクト
        """
        db_path = os.path.join(self.cache_dir, "stocks_board", f"{code}.duckdb")
        if not os.path.exists(db_path):
            if len(code) > 4:
                code_retry = code[:-1]
                # 再帰呼び出しの結果を返す（ジェネレータなので yield from）
                yield from self.get_db(code_retry)
                return

            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            logger.info(f"DuckDBファイルを作成しました: {db_path}")

        db = duckdb.connect(db_path)
        try:
            yield db
        finally:
            db.close()
