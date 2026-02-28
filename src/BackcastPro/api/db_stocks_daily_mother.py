from .db_stocks_daily import db_stocks_daily
from typing import Optional
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class db_stocks_daily_mother(db_stocks_daily):
    """全銘柄統合 DuckDB マネージャ

    mother.duckdb に全銘柄の stocks_daily データを格納する。
    _db_subdir=None により _get_db_path() が _db_filename ブランチを使い、
    get_db(code) が常に同一の mother.duckdb を返す。
    save_stock_prices / load_stock_prices_from_cache は親クラスをそのまま再利用。
    """

    _db_subdir   = None
    _db_filename = "stocks_daily/mother.duckdb"  # → {cache_dir}/jp/stocks_daily/mother.duckdb

    def split_to_individual(
        self,
        individual_db,              # db_stocks_daily インスタンス（= sp.db）
        codes: list[str] = None,
        from_date: Optional[str] = None,  # None → 全期間（初回移行時）
    ) -> dict:
        """mother.duckdb → 個別 {code}.duckdb へ分割（冪等）

        get_db() は1回のみオープン（コードリスト取得も同じ接続内で実施）。
        individual_db.save_stock_prices() の重複チェックにより冪等に動作する。

        Args:
            individual_db: 個別DBへの保存先インスタンス（通常は sp.db）
            codes: 対象銘柄コードリスト。None の場合は mother.duckdb 内の全銘柄
            from_date: 分割対象の開始日（YYYY-MM-DD）。None の場合は全期間

        Returns:
            {"success": int, "failed": int, "errors": list[str]}
        """
        success, failed, errors = 0, 0, []

        with self.get_db() as db:
            if codes is None:
                if not self._table_exists(db, "stocks_daily"):
                    return {"success": 0, "failed": 0, "errors": []}
                codes = [r[0] for r in db.execute(
                    'SELECT DISTINCT "Code" FROM stocks_daily ORDER BY "Code"'
                ).fetchall()]

            for i, code in enumerate(codes, 1):
                try:
                    query = ('SELECT "Code","Date","Open","High","Low","Close","Volume" '
                             'FROM stocks_daily WHERE "Code" = ?')
                    params = [code]
                    if from_date:
                        query += ' AND "Date" >= ?'
                        params.append(from_date)
                    df = db.execute(query, params).fetchdf()
                    if df.empty:
                        failed += 1
                        errors.append(code)
                        continue
                    df["Date"] = pd.to_datetime(df["Date"])
                    individual_db.save_stock_prices(code, df)
                    success += 1
                except Exception as e:
                    logger.error(f"{code}: {e}")
                    failed += 1
                    errors.append(code)
                if i % 500 == 0 or i == len(codes):
                    logger.info(f"split進捗 {i}/{len(codes)} 成功={success} 失敗={failed}")

        return {"success": success, "failed": failed, "errors": errors}
