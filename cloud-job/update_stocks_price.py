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
    python update_stocks_price.py --workers 8        # 並列ワーカー数を指定
"""

import os
import sys
import logging
import argparse
import threading
import queue
import time
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging.handlers import RotatingFileHandler

import pandas as pd

from trading_data.stocks_price import stocks_price
from trading_data.stocks_info import stocks_info
from trading_data.lib.e_api import e_api
from trading_data.lib.jquants import jquants as jquants_cls

logger = logging.getLogger(__name__)


@dataclass
class UpdateSummary:
    """更新処理のサマリー"""

    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    total_stocks: int = 0
    success_count: int = 0
    failed_count: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


def setup_logging() -> logging.Logger:
    """ログ設定（コンソール＋ファイル）"""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # コンソールハンドラ
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
        )
    )
    root_logger.addHandler(console_handler)

    # ファイルハンドラ（ログファイル出力）
    cache_dir = os.environ.get("STOCKDATA_CACHE_DIR", ".")
    log_dir = os.path.join(cache_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(
        log_dir, f"update_stocks_price_{datetime.now().strftime('%Y%m%d')}.log"
    )

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    root_logger.addHandler(file_handler)

    return logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """コマンドライン引数をパース"""
    parser = argparse.ArgumentParser(description="夜間株価取得スクリプト")
    parser.add_argument(
        "--codes", type=str, help="処理対象の銘柄コード（カンマ区切り）例: 7203,8306"
    )
    parser.add_argument(
        "--days", type=int, default=7, help="取得する過去日数（デフォルト: 7）"
    )
    parser.add_argument(
        "--workers", type=int, default=4, help="並列ワーカー数（デフォルト: 4）"
    )
    return parser.parse_args()


def get_stock_codes_list() -> list[str]:
    """J-Quantsから銘柄コードリストを取得"""
    logger.info("銘柄リスト取得中...")
    si = stocks_info()
    df = si._fetch_from_jquants()

    if df is None or df.empty:
        logger.error("銘柄リストの取得に失敗しました")
        return []

    # Code列から銘柄コードを取得
    if "Code" in df.columns:
        codes = df["Code"].astype(str).tolist()
    elif "code" in df.columns:
        codes = df["code"].astype(str).tolist()
    else:
        logger.error("銘柄リストにCode列がありません")
        return []

    # 4桁に正規化（末尾の0を除去）
    normalized_codes = []
    for code in codes:
        code = code.strip()
        if len(code) == 5 and code.endswith("0"):
            code = code[:4]
        normalized_codes.append(code)

    logger.info(f"銘柄リスト取得完了: {len(normalized_codes)} 銘柄")
    return normalized_codes


def get_fetch_date_range(days: int = 7) -> tuple[datetime, datetime]:
    """取得対象の日付範囲を決定"""
    now = datetime.now()
    to_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from_date = to_date - timedelta(days=days)
    return from_date, to_date


def merge_with_jquants_priority(
    base_df: pd.DataFrame | None, jquants_df: pd.DataFrame
) -> pd.DataFrame:
    """
    base_df と jquants_df をマージ。同一日付は J-Quants で上書き。

    Args:
        base_df: tachibana または stooq から取得したデータ
        jquants_df: J-Quants から取得したデータ（優先）

    Returns:
        マージ済みDataFrame
    """
    if base_df is None or base_df.empty:
        return jquants_df

    # インデックスをDateに統一
    base_copy = base_df.copy()
    jq_copy = jquants_df.copy()

    if "Date" in base_copy.columns:
        base_copy = base_copy.set_index("Date")
    if "Date" in jq_copy.columns:
        jq_copy = jq_copy.set_index("Date")

    # base_df から jquants_df にない日付のみ抽出
    base_only = base_copy.loc[~base_copy.index.isin(jq_copy.index)]

    # jquants_df と base_only を結合
    merged = pd.concat([jq_copy, base_only]).sort_index()

    return merged


def _fetch_with_retry(
    fetch_fn,
    code: str,
    from_: datetime,
    to: datetime,
    max_attempts: int = 3,
) -> pd.DataFrame | None:
    """指数バックオフ付きリトライ（Stooq/J-Quants用）"""
    for attempt in range(1, max_attempts + 1):
        try:
            return fetch_fn(code, from_, to)
        except Exception:
            if attempt == max_attempts:
                raise
            wait = min(1 * (2 ** (attempt - 1)), 10)
            logger.debug(f"  Retry {attempt}/{max_attempts} for {code}, wait {wait}s")
            time.sleep(wait)


def process_stock(
    code: str,
    tachibana_df: pd.DataFrame | None,
    from_date: datetime,
    to_date: datetime,
) -> tuple[str, bool, int, str | None]:
    """
    パイプラインのConsumer: Tachibana結果を受け取り
    Stooqフォールバック → J-Quants取得 → マージ → DuckDB保存
    """
    sp = stocks_price()
    base_df = tachibana_df
    source = "tachibana" if (base_df is not None and not base_df.empty) else None

    # Stooq fallback（Tachibana失敗時のみ）
    if base_df is None or base_df.empty:
        try:
            base_df = _fetch_with_retry(sp._fetch_from_stooq, code, from_date, to_date)
            if base_df is not None and not base_df.empty:
                source = "stooq"
                logger.debug(f"  Stooq {code}: {len(base_df)} records")
        except Exception as e:
            logger.debug(f"  Stooq {code} failed: {e}")

    # J-Quants（常に取得）
    jquants_df = None
    try:
        jquants_df = _fetch_with_retry(sp._fetch_from_jquants, code, from_date, to_date)
        if jquants_df is not None and not jquants_df.empty:
            logger.debug(f"  J-Quants {code}: {len(jquants_df)} records")
    except Exception as e:
        logger.debug(f"  J-Quants {code} failed: {e}")

    # マージ（J-Quants優先）
    if jquants_df is not None and not jquants_df.empty:
        final_df = merge_with_jquants_priority(base_df, jquants_df)
        final_source = "jquants" if source is None else f"{source}+jquants"
    else:
        final_df = base_df
        final_source = source

    # DuckDB保存
    if final_df is not None and not final_df.empty:
        sp.db.save_stock_prices(code, final_df)
        return code, True, len(final_df), final_source
    return code, False, 0, None


def main():
    """メインエントリーポイント"""
    global logger
    logger = setup_logging()

    args = parse_arguments()

    logger.info("=" * 50)
    logger.info("夜間株価取得開始")
    logger.info("=" * 50)

    summary = UpdateSummary()

    # 1. 銘柄リスト取得
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",")]
        logger.info(f"指定銘柄: {codes}")
    else:
        codes = get_stock_codes_list()

    if not codes:
        logger.error("処理対象の銘柄がありません")
        return 1

    summary.total_stocks = len(codes)

    # 2. 日付範囲決定
    from_date, to_date = get_fetch_date_range(args.days)
    logger.info(
        f"取得期間: {from_date.strftime('%Y-%m-%d')} 〜 {to_date.strftime('%Y-%m-%d')}"
    )

    # 3. パイプライン方式で株価取得
    #    Producer: Tachibana直列 → Queue → Consumer: Stooq/J-Quants/Save並列
    sp = stocks_price()
    # シングルトンをスレッド開始前に事前初期化
    # （スレッド間の lazy-init 競合を防止）
    sp.e_shiten = e_api()
    sp.jq = jquants_cls()
    modified_codes = []
    tachibana_queue = queue.Queue()

    def tachibana_producer():
        """Tachibana APIを直列で呼び出し、結果をキューに流す"""
        try:
            for i, code in enumerate(codes, 1):
                tachi_df = None
                try:
                    tachi_df = sp._fetch_from_tachibana(code, from_date, to_date)
                    if tachi_df is not None and not tachi_df.empty:
                        logger.debug(
                            f"  [{i}/{len(codes)}] Tachibana {code}: "
                            f"{len(tachi_df)} records"
                        )
                except Exception as e:
                    logger.debug(f"  Tachibana {code} failed: {e}")
                tachibana_queue.put((code, tachi_df))
        finally:
            tachibana_queue.put(None)  # 終了シグナル（必ず送信）

    producer = threading.Thread(target=tachibana_producer, daemon=True)
    producer.start()

    logger.info(f"パイプライン開始 (workers={args.workers})")

    futures = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # キューからTachibana結果を受け取り、Consumer に投入
        while True:
            item = tachibana_queue.get()
            if item is None:
                break
            code, tachi_df = item
            future = executor.submit(process_stock, code, tachi_df, from_date, to_date)
            futures[future] = code

        # 全Consumerの完了を待ち、結果を集計
        total = len(futures)
        completed = 0
        for future in as_completed(futures):
            completed += 1
            try:
                code, ok, count, source = future.result()
                if ok:
                    modified_codes.append(code)
                    summary.success_count += 1
                    logger.debug(
                        f"  {code} → 成功 (source: {source}, records: {count})"
                    )
                else:
                    summary.failed_count += 1
                    summary.errors.append((code, "No data returned"))
                    logger.warning(f"  {code} → データなし")
            except Exception as e:
                code = futures[future]
                summary.failed_count += 1
                summary.errors.append((code, str(e)))
                logger.error(f"  {code} → 失敗: {e}")
            if completed % 100 == 0 or completed == total:
                logger.info(
                    f"進捗: {completed}/{total} "
                    f"(成功={summary.success_count}, "
                    f"失敗={summary.failed_count})"
                )

    producer.join()

    # 4. サマリー出力
    summary.end_time = datetime.now()
    duration = summary.end_time - summary.start_time

    logger.info("=" * 50)
    logger.info("処理完了サマリー")
    logger.info("=" * 50)
    logger.info(f"処理時間: {duration}")
    logger.info(f"対象銘柄: {summary.total_stocks}")
    logger.info(f"成功: {summary.success_count}")
    logger.info(f"失敗: {summary.failed_count}")

    if summary.errors:
        logger.info("-" * 50)
        logger.info("エラー詳細:")
        for code, error in summary.errors[:10]:  # 最大10件
            logger.info(f"  {code}: {error}")
        if len(summary.errors) > 10:
            logger.info(f"  ... 他 {len(summary.errors) - 10} 件")

    return 0 if summary.failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
