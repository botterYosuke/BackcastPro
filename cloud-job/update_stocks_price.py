"""
夜間株価取得スクリプト

複数のデータソースから株価を取得し、DuckDBに保存する。

取得優先度:
1. J-Quants を試行
2. J-Quants 失敗時は Tachibana（立花証券 e-支店）を試行
3. Tachibana 失敗時は Stooq を試行

使用方法:
    python update_stocks_price.py                    # 全銘柄処理
    python update_stocks_price.py --codes 7203,8306  # 特定銘柄のみ
    python update_stocks_price.py --days 14           # 取得日数を指定
"""

import os
import sys
import time
import logging
import argparse
import tempfile
from datetime import datetime, timedelta

import pandas as pd

# STOCKDATA_CACHE_DIR をそのまま利用
_base = os.environ.get("STOCKDATA_CACHE_DIR", tempfile.mkdtemp())
os.environ["STOCKDATA_CACHE_DIR"] = os.path.abspath(_base)

from trading_data.stocks_price import stocks_price
from trading_data.stocks_info import stocks_info
from trading_data.lib.e_api import e_api
from trading_data.lib.jquants import jquants as jquants_cls
from BackcastPro.api.db_stocks_daily_mother import db_stocks_daily_mother

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="夜間株価取得スクリプト")
    parser.add_argument(
        "--codes", type=str, help="処理対象の銘柄コード（カンマ区切り）例: 7203,8306"
    )
    parser.add_argument(
        "--days", type=int, default=7, help="取得する過去日数（デフォルト: 7）"
    )
    return parser.parse_args()



def main():
    args = parse_arguments()

    # 銘柄リスト取得
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",")]
    else:
        logger.info("銘柄リスト取得中...")
        si = stocks_info()
        df = si._fetch_from_jquants()
        if df is None or df.empty:
            logger.error("銘柄リストの取得に失敗しました")
            return 1
        codes = df["Code"].astype(str).tolist()

    logger.info(f"対象銘柄数: {len(codes)}")

    # 日付範囲
    to_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    from_date = to_date - timedelta(days=args.days)
    logger.info(f"取得期間: {from_date:%Y-%m-%d} 〜 {to_date:%Y-%m-%d}")

    # シングルトン事前初期化
    sp = stocks_price()
    sp.e_shiten = e_api()
    sp.jq = jquants_cls()
    mother_db = db_stocks_daily_mother()

    # J-Quants 一括プリフェッチ（日付ごとに全銘柄を取得してメモリ上にキャッシュ）
    logger.info("J-Quants 一括取得中...")
    jq_bulk_dfs: dict[str, "pd.DataFrame"] = {}  # code (4桁) -> DataFrame

    if sp.jq.isEnable and not args.codes:
        all_bulk: list["pd.DataFrame"] = []
        date_range = [
            (from_date + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((to_date - from_date).days + 1)
        ]
        for date_str in date_range:
            try:
                bulk_df = sp.jq.get_daily_quotes_bulk_by_date(date_str)
                if bulk_df is not None and not bulk_df.empty:
                    all_bulk.append(bulk_df)
            except Exception as e:
                logger.warning(f"Bulk fetch 失敗 ({date_str}): {e}")

        if all_bulk:
            combined = pd.concat(all_bulk, ignore_index=True)
            # Code を4桁に変換してから groupby（codes リストが4桁のため）
            combined["Code"] = combined["Code"].str[:4]
            jq_bulk_dfs = dict(tuple(combined.groupby("Code")))

    logger.info(f"J-Quants 一括取得完了: {len(jq_bulk_dfs)} 銘柄")

    # 逐次処理
    success, failed, errors = 0, 0, []

    for i, code in enumerate(codes, 1):
        # 1) J-Quants（バルクキャッシュ優先、未取得時のみAPIコール）
        final_df = jq_bulk_dfs.get(code)
        if final_df is None:
            for attempt in range(3):
                try:
                    final_df = sp._fetch_from_jquants(code, from_date, to_date)
                    if final_df is not None and not final_df.empty:
                        break
                except Exception:
                    pass
                if attempt < 2:
                    time.sleep(1)

        # 2) J-Quants 失敗 → Tachibana
        if final_df is None or final_df.empty:
            try:
                final_df = sp._fetch_from_tachibana(code, from_date, to_date)
            except Exception:
                pass

        # 3) Tachibana 失敗 → Stooq
        if final_df is None or final_df.empty:
            try:
                final_df = sp._fetch_from_stooq(code, from_date, to_date)
            except Exception:
                pass

        # DatetimeIndex 正規化（全ソース共通・無条件に実行）
        if final_df is not None and not final_df.empty:
            if "Date" in final_df.columns:
                final_df = final_df.set_index("Date")
            if not isinstance(final_df.index, pd.DatetimeIndex):
                final_df.index = pd.to_datetime(final_df.index)
            final_df.index.name = "Date"

        # 保存
        if final_df is not None and not final_df.empty:
            try:
                mother_db.save_stock_prices(code, final_df)
                success += 1
            except Exception as e:
                logger.error(f"銘柄 {code} の保存に失敗: {e}")
                failed += 1
                errors.append(code)
        else:
            failed += 1
            errors.append(code)

        if i % 100 == 0 or i == len(codes):
            logger.info(f"進捗: {i}/{len(codes)} (成功={success}, 失敗={failed})")

    # mother.duckdb → 個別DB 分割
    logger.info("mother.duckdb → 個別DB 分割開始...")
    split_result = mother_db.split_to_individual(
        sp.db, from_date=from_date.strftime("%Y-%m-%d")
    )
    logger.info(f"split完了: 成功={split_result['success']}, 失敗={split_result['failed']}")

    # サマリー
    logger.info(f"完了: 成功={success}, 失敗={failed}")
    if errors:
        logger.info(f"エラー銘柄: {errors[:10]}")
        if len(errors) > 10:
            logger.info(f"  ... 他 {len(errors) - 10} 件")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
