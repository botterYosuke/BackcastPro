"""
夜間株価取得スクリプト

複数のデータソースから株価を取得し、DuckDBに保存する。

取得優先度:
1. Tachibana（立花証券 e-支店）を試行
2. Tachibana失敗時は Stooq を試行
3. 1 or 2 の成功に関わらず J-Quants も取得し、J-Quantsのデータで上書き

使用方法:
    python update_stocks_price.py                    # 全銘柄処理
    python update_stocks_price.py --codes 7203,8306  # 特定銘柄のみ
    python update_stocks_price.py --days 14           # 取得日数を指定
"""

import sys
import logging
import argparse
from datetime import datetime, timedelta

import pandas as pd

from trading_data.stocks_price import stocks_price
from trading_data.stocks_info import stocks_info
from trading_data.lib.e_api import e_api
from trading_data.lib.jquants import jquants as jquants_cls

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


def merge_jquants_priority(
    base_df: pd.DataFrame | None, jq_df: pd.DataFrame | None
) -> pd.DataFrame | None:
    """base_df と jq_df をマージ。同一日付は J-Quants で上書き。"""
    if jq_df is None or jq_df.empty:
        return base_df
    if base_df is None or base_df.empty:
        return jq_df

    base = base_df.set_index("Date") if "Date" in base_df.columns else base_df.copy()
    jq = jq_df.set_index("Date") if "Date" in jq_df.columns else jq_df.copy()

    base_only = base.loc[~base.index.isin(jq.index)]
    return pd.concat([jq, base_only]).sort_index()


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

    # 逐次処理
    success, failed, errors = 0, 0, []

    for i, code in enumerate(codes, 1):
        base_df = None

        # 1) Tachibana
        try:
            base_df = sp._fetch_from_tachibana(code, from_date, to_date)
        except Exception:
            pass

        # 2) Stooq fallback
        if base_df is None or base_df.empty:
            try:
                base_df = sp._fetch_from_stooq(code, from_date, to_date)
            except Exception:
                pass

        # 3) J-Quants（常に取得→優先マージ）
        jq_df = None
        try:
            jq_df = sp._fetch_from_jquants(code, from_date, to_date)
        except Exception:
            pass

        # マージ & 保存
        final_df = merge_jquants_priority(base_df, jq_df)
        if final_df is not None and not final_df.empty:
            sp.db.save_stock_prices(code, final_df)
            success += 1
        else:
            failed += 1
            errors.append(code)

        if i % 100 == 0 or i == len(codes):
            logger.info(f"進捗: {i}/{len(codes)} (成功={success}, 失敗={failed})")

    # サマリー
    logger.info(f"完了: 成功={success}, 失敗={failed}")
    if errors:
        logger.info(f"エラー銘柄: {errors[:10]}")
        if len(errors) > 10:
            logger.info(f"  ... 他 {len(errors) - 10} 件")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
