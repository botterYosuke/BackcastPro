"""
株式ランキングデータの保存・読み込みを管理するモジュール

ランキング種別:
  price_rankings テーブル (銘柄別 7種):
    gain_rate, decline_rate, volume_high, turnover_value,
    tick_count, volume_surge, turnover_surge
  sector_rankings テーブル (業種別 2種):
    sector_gain_rate, sector_decline_rate
"""

from .db_manager import db_manager
import pandas as pd
import duckdb
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class db_stocks_ranking(db_manager):
    """ランキングデータ専用 DuckDB マネージャ"""

    _db_filename = "stocks_ranking.duckdb"
    # _db_subdir は設定しない → {cache_dir}/jp/stocks_ranking.duckdb に配置

    def __init__(self):
        super().__init__()

    # ------------------------------------------------------------------
    # テーブル作成
    # ------------------------------------------------------------------
    def ensure_tables(self) -> None:
        """price_rankings / sector_rankings テーブルを作成（存在しなければ）"""
        with self.get_db() as db:
            # 銘柄別ランキング (7種)
            db.execute("""
                CREATE TABLE IF NOT EXISTS price_rankings (
                    "Date"              DATE         NOT NULL,
                    "RankType"          VARCHAR(50)  NOT NULL,
                    "Rank"              INTEGER      NOT NULL,
                    "Code"              VARCHAR(10),
                    "CompanyName"       VARCHAR,
                    "Sector17Code"      VARCHAR(10),
                    "Sector17CodeName"  VARCHAR,
                    "Value"             DOUBLE,
                    PRIMARY KEY ("Date", "RankType", "Rank")
                )
            """)
            # 業種別ランキング (2種)
            db.execute("""
                CREATE TABLE IF NOT EXISTS sector_rankings (
                    "Date"              DATE         NOT NULL,
                    "RankType"          VARCHAR(50)  NOT NULL,
                    "Rank"              INTEGER      NOT NULL,
                    "Sector17Code"      VARCHAR(10),
                    "Sector17CodeName"  VARCHAR(100),
                    "Value"             DOUBLE,
                    "StockCount"        INTEGER,
                    PRIMARY KEY ("Date", "RankType", "Rank")
                )
            """)
            logger.info("ランキングテーブルの準備完了")

    # ------------------------------------------------------------------
    # 保存 (共通: DELETE → INSERT)
    # ------------------------------------------------------------------
    def save_rankings(self, date: str, table: str, df: pd.DataFrame) -> None:
        """
        ランキングデータを保存（冪等: 既存データは DELETE してから INSERT）

        Args:
            date: 対象日 (YYYY-MM-DD)
            table: "price_rankings" or "sector_rankings"
            df: 保存するデータ（テーブルカラムに合致する DataFrame）
        """
        if df is None or df.empty:
            logger.warning(f"保存データが空です: {table} / {date}")
            return

        valid_tables = ("price_rankings", "sector_rankings")
        if table not in valid_tables:
            raise ValueError(f"無効なテーブル名: {table} (有効: {valid_tables})")

        with self.get_db() as db:
            db.execute("BEGIN TRANSACTION")
            try:
                # 対象日の該当 RankType を一括削除
                rank_types = df["RankType"].unique().tolist()
                for rt in rank_types:
                    db.execute(
                        f'DELETE FROM {table} WHERE "Date" = ? AND "RankType" = ?',
                        [date, rt],
                    )

                # INSERT
                db.register("_tmp_ranking", df)
                cols = ", ".join(f'"{c}"' for c in df.columns)
                db.execute(
                    f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _tmp_ranking"
                )
                db.unregister("_tmp_ranking")

                db.execute("COMMIT")
                logger.info(
                    f"保存完了: {table} / {date} — {len(df)} 件 "
                    f"(RankType: {rank_types})"
                )

            except Exception as e:
                db.execute("ROLLBACK")
                logger.error(f"保存失敗: {table} / {date} — {e}")
                raise

    # ------------------------------------------------------------------
    # 読み込み (共通)
    # ------------------------------------------------------------------
    def load_rankings(
        self, date: str, table: str, rank_type: str = None
    ) -> pd.DataFrame:
        """
        ランキングデータを読み込む

        Args:
            date: 対象日 (YYYY-MM-DD)
            table: "price_rankings" or "sector_rankings"
            rank_type: 絞り込む RankType（省略時は全 RankType）
        """
        valid_tables = ("price_rankings", "sector_rankings")
        if table not in valid_tables:
            raise ValueError(f"無効なテーブル名: {table} (有効: {valid_tables})")

        with self.get_db() as db:
            if not self._table_exists(db, table):
                return pd.DataFrame()

            params = [date]
            query = f'SELECT * FROM {table} WHERE "Date" = ?'
            if rank_type:
                query += ' AND "RankType" = ?'
                params.append(rank_type)
            query += ' ORDER BY "RankType", "Rank"'

            return db.execute(query, params).fetchdf()
