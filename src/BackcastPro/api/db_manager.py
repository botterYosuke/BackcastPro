import os
import pandas as pd
import duckdb
import logging
import inspect
import tempfile

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class db_manager:
    """
    データベース管理クラス
    キャッシュやデータの保存・読み込みを担当
    """

    def __init__(self):
        # 1. 環境変数をチェック
        env_cache_dir = os.environ.get('BACKCASTPRO_CACHE_DIR', tempfile.mkdtemp())
        self.cache_dir = os.path.abspath(env_cache_dir)
        os.environ['BACKCASTPRO_CACHE_DIR'] = self.cache_dir

        # 3. ディレクトリが存在しない場合は作成
        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir, exist_ok=True)
                logger.info(f"キャッシュディレクトリを作成しました: {self.cache_dir}")
                self.isEnable = True
            except Exception as e:
                logger.warning(f"キャッシュディレクトリの作成に失敗しました: {self.cache_dir}, エラー: {e}")
                self.isEnable = False
        else:
            self.isEnable = True
        
        # デバッグ情報をログ出力
        logger.info(f"キャッシュディレクトリ: {self.cache_dir}")
        logger.info(f"キャッシュディレクトリ存在チェック: {self.isEnable}")
        if not self.isEnable:
            logger.warning(f"キャッシュディレクトリが存在しないか、アクセスできません: {self.cache_dir}")


    def _table_exists(self, db_connection: duckdb.DuckDBPyConnection, table_name: str) -> bool:
        """テーブルが存在するかチェック"""
        try:
            result = db_connection.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", 
                [table_name]
            ).fetchone()
            return result[0] > 0
        except:
            return False


    def _create_table_from_dataframe(self, 
        db_connection: duckdb.DuckDBPyConnection, 
        table_name: str, 
        df: pd.DataFrame, 
        primary_keys: list = None) -> None:
        """
        DataFrameの構造に基づいて動的にテーブルを作成
        
        Args:
            table_name (str): 作成するテーブル名
            df (pd.DataFrame): テーブル構造の基準となるDataFrame
            primary_keys (list): プライマリキーとするカラム名のリスト
        """
        if df is None or df.empty:
            raise ValueError("DataFrameが空です。テーブル構造を決定できません。")
        
        # カラム名とデータ型を取得
        columns = []
        for col in df.columns:
            # データ型を推定してSQL型に変換
            dtype = df[col].dtype
            if pd.api.types.is_integer_dtype(dtype):
                sql_type = "BIGINT"
            elif pd.api.types.is_float_dtype(dtype):
                sql_type = "DOUBLE"
            elif pd.api.types.is_datetime64_any_dtype(dtype):
                sql_type = "TIMESTAMP"
            elif pd.api.types.is_bool_dtype(dtype):
                sql_type = "BOOLEAN"
            else:
                # 文字列型の場合、最大長を推定
                max_length = df[col].astype(str).str.len().max()
                if pd.isna(max_length) or max_length == 0:
                    max_length = 255
                else:
                    max_length = min(max_length * 2, 1000)  # 余裕を持たせる
                sql_type = f"VARCHAR({max_length})"
            
            # 列名はダブルクオートで明示して大文字小文字を保持
            columns.append(f'"{col}" {sql_type}')
        
        # プライマリキーの設定
        if primary_keys:
            # PK も列名をダブルクオートで明示
            pk_columns = ", ".join([f'"{c}"' for c in primary_keys])
            columns.append(f"PRIMARY KEY ({pk_columns})")
        
        # メタデータカラムを追加
        columns.extend([
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ])
        
        # CREATE TABLE文を構築
        # テーブルが既に存在する場合は作成をスキップ
        if not self._table_exists(db_connection, table_name):
            create_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns)})"
            
            # テーブルを作成
            try:
                db_connection.execute(create_sql)
                logger.info(f"テーブル '{table_name}' を動的に作成しました")
            except Exception as e:
                # テーブル作成中に他のスレッドが作成した可能性があるため、再度チェック
                if self._table_exists(db_connection, table_name):
                    logger.info(f"テーブル '{table_name}' は既に存在します（他のスレッドが作成した可能性）")
                else:
                    # それ以外のエラーは再スロー
                    raise e
        else:
            logger.info(f"テーブル '{table_name}' は既に存在します")
        

    def _convert_df_to_list(self, df: pd.DataFrame) -> list:
        """
        DataFrameを辞書のリスト形式に変換

        Args:
            df (pd.DataFrame): 変換するDataFrame

        Returns:
            list: 各行が辞書形式のリスト
        """
        # 空のDataFrameは空リストを返す
        if df is None or df.empty:
            return []
        
        # DataFrameを辞書形式に変換
        # orient='records'で各行を辞書として変換
        return df.to_dict(orient='records')


    def __add_db__(self, db_connection: duckdb.DuckDBPyConnection, table_name: str, df: pd.DataFrame, key: str):

        # カラム整合性チェック
        self._validate_table_schema(db_connection, table_name, df, key)
        
        # 既存のkeyのみを取得（パフォーマンス最適化）
        existing_count = db_connection.execute(f"SELECT COUNT(*) as count FROM {table_name}").fetchone()[0]
        
        if existing_count == 0:
            # 既存データが空の場合は全データを挿入
            logger.info("既存データが空のため、全データを挿入します")
            self._batch_insert_data(db_connection, table_name, df)
        else:
            # 既存データと新データを比較してユニークな行のみを追加
            if key in df.columns:
                # 既存のkeyのみを効率的に取得
                existing_disclosure_numbers = set(
                    db_connection.execute(
                        f"SELECT DISTINCT {key} FROM {table_name}"
                    ).fetchdf()[key].astype(str)
                )
                
                new_disclosure_numbers = set(df[key].astype(str))
                
                # 新規のkeyのみを抽出
                unique_disclosure_numbers = new_disclosure_numbers - existing_disclosure_numbers
                
                if unique_disclosure_numbers:
                    # 新規データのみをフィルタリング
                    new_data_df = df[df[key].astype(str).isin(unique_disclosure_numbers)]
                    
                    logger.info(f"新規データ {len(new_data_df)} 件を追加します")
                    
                    # バッチで新規データを挿入
                    self._batch_insert_data(db_connection, table_name, new_data_df)
                else:
                    logger.info("新規データはありません")
            else:
                # keyがない場合は全データを挿入（重複チェックなし）
                logger.warning(f"{key}カラムが見つからないため、全データを挿入します")
                self._batch_insert_data(db_connection, table_name, df)

    def __create_db__(self, db_connection: duckdb.DuckDBPyConnection, table_name: str, df: pd.DataFrame, key: str):
        # keyカラムをプライマリキーとして設定（存在する場合）
        primary_keys = [key] if key in df.columns else None
        self._create_table_from_dataframe(db_connection, table_name, df, primary_keys)

        # インデックスをkeyに作成
        if key in df.columns:
            db_connection.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_{key} ON {table_name}("{key}")')
        
        # バッチでデータを挿入
        self._batch_insert_data(db_connection, table_name, df)


    def _validate_table_schema(self, db_connection: duckdb.DuckDBPyConnection, table_name: str, df: pd.DataFrame, key: str) -> None:
        """
        既存テーブルと新データのカラム整合性をチェック
        
        Args:
            table_name (str): テーブル名
            df (pd.DataFrame): 新データ
        
        Raises:
            ValueError: カラム構造に不整合がある場合
        """
        try:
            # テーブルのカラム情報を取得
            table_info = db_connection.execute(f"PRAGMA table_info({table_name})").fetchdf()
            existing_columns = set(table_info['name'].tolist())
            new_columns = set(df.columns.tolist())
            
            # メタデータカラムは自動設定されるため、チェック対象から除外
            metadata_columns = {'created_at', 'updated_at'}
            existing_columns_without_metadata = existing_columns - metadata_columns
            
            # カラムの差分をチェック
            missing_columns = existing_columns_without_metadata - new_columns
            extra_columns = new_columns - existing_columns_without_metadata
            
            if missing_columns or extra_columns:
                warning_msg = f"カラム構造の不一致を検出しました - テーブル: {table_name}"
                if missing_columns:
                    warning_msg += f"\n  新データに不足: {sorted(missing_columns)}"
                if extra_columns:
                    warning_msg += f"\n  新データに追加: {sorted(extra_columns)}"
                
                logger.warning(warning_msg)
                
                # 重要なカラム（key）が不足している場合はエラー
                if key in missing_columns:
                    raise ValueError(f"新データに{key}カラムが存在しません")
            
        except Exception as e:
            logger.error(f"カラム整合性チェック中にエラーが発生しました: {str(e)}")
            # スキーマチェックでのエラーは警告レベルにとどめ、処理は継続
            if key in str(e):
                raise


    def _batch_insert_data(self, db_connection: duckdb.DuckDBPyConnection, table_name: str, df: pd.DataFrame, batch_size: int = 1000) -> None:
        """
        大量データを効率的にバッチ挿入
        
        Args:
            db_connection (duckdb.DuckDBPyConnection): DuckDB接続
            table_name (str): 挿入先テーブル名
            df (pd.DataFrame): 挿入するデータ
            batch_size (int): バッチサイズ（デフォルト: 1000件）
        """
        total_rows = len(df)
        
        if total_rows <= batch_size:
            # 小さなデータは一括挿入
            db_connection.register('temp_df', df)
            df_columns = ", ".join(df.columns)
            # DuckDBではINSERT OR REPLACEの代わりにINSERTを使用（重複チェックは呼び出し元で実施）
            db_connection.execute(f"INSERT INTO {table_name} ({df_columns}) SELECT {df_columns} FROM temp_df")
            logger.debug(f"データを一括挿入しました: {total_rows}件")
        else:
            # 大量データはチャンクに分割して挿入
            logger.info(f"大量データをバッチ処理で挿入します: {total_rows}件 (バッチサイズ: {batch_size})")
            
            for i in range(0, total_rows, batch_size):
                chunk = df.iloc[i:i+batch_size]
                chunk_name = f'statements_chunk_{i//batch_size}'
                
                db_connection.register(chunk_name, chunk)
                df_columns = ", ".join(chunk.columns)
                # DuckDBではINSERT OR REPLACEの代わりにINSERTを使用（重複チェックは呼び出し元で実施）
                db_connection.execute(f"INSERT INTO {table_name} ({df_columns}) SELECT {df_columns} FROM {chunk_name}")
                
                # 進捗をログ出力
                processed = min(i + batch_size, total_rows)
                logger.debug(f"バッチ挿入進捗: {processed}/{total_rows} 件 ({processed/total_rows*100:.1f}%)")
            
            logger.info(f"バッチ挿入完了: {total_rows}件")
