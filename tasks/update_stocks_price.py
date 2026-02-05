"""
夜間株価取得・FTPアップロードスクリプト

複数のデータソースから株価を取得し、DuckDBにキャッシュ保存後、FTPサーバーにアップロードする。

取得優先度:
1. Tachibana（立花証券 e-支店）を試行
2. Tachibana失敗時は Stooq を試行
3. 1 or 2 の成功に関わらず J-Quants も取得し、J-Quantsのデータで上書き

使用方法:
    python update_stocks_price.py                    # 全銘柄処理
    python update_stocks_price.py --codes 7203,8306  # 特定銘柄のみ
    python update_stocks_price.py --dry-run          # FTPアップロードをスキップ
"""
import os
import sys
import logging
import argparse
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler

import pandas as pd

from TradingData.stocks_price import stocks_price
from TradingData.stocks_info import stocks_info

logger = logging.getLogger(__name__)


@dataclass
class UpdateSummary:
    """更新処理のサマリー"""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    total_stocks: int = 0
    success_count: int = 0
    failed_count: int = 0
    ftp_uploaded: int = 0
    ftp_failed: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


def setup_logging() -> logging.Logger:
    """ログ設定（コンソール＋ファイル）"""
    cache_dir = os.environ.get('BACKCASTPRO_CACHE_DIR', '.')
    log_dir = os.path.join(cache_dir, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(
        log_dir,
        f"update_stocks_price_{datetime.now().strftime('%Y%m%d')}.log"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # コンソールハンドラ
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    ))

    # ファイルハンドラ（ローテーション）
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    return logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """コマンドライン引数をパース"""
    parser = argparse.ArgumentParser(
        description='夜間株価取得・FTPアップロードスクリプト'
    )
    parser.add_argument(
        '--codes',
        type=str,
        help='処理対象の銘柄コード（カンマ区切り）例: 7203,8306'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='FTPアップロードをスキップ'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='取得する過去日数（デフォルト: 7）'
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
    if 'Code' in df.columns:
        codes = df['Code'].astype(str).tolist()
    elif 'code' in df.columns:
        codes = df['code'].astype(str).tolist()
    else:
        logger.error("銘柄リストにCode列がありません")
        return []

    # 4桁に正規化（末尾の0を除去）
    normalized_codes = []
    for code in codes:
        code = code.strip()
        if len(code) == 5 and code.endswith('0'):
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
    base_df: pd.DataFrame | None,
    jquants_df: pd.DataFrame
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

    if 'Date' in base_copy.columns:
        base_copy = base_copy.set_index('Date')
    if 'Date' in jq_copy.columns:
        jq_copy = jq_copy.set_index('Date')

    # base_df から jquants_df にない日付のみ抽出
    base_only = base_copy.loc[~base_copy.index.isin(jq_copy.index)]

    # jquants_df と base_only を結合
    merged = pd.concat([jq_copy, base_only]).sort_index()

    return merged


def fetch_and_merge_stock_price(
    sp: stocks_price,
    code: str,
    from_: datetime,
    to: datetime
) -> tuple[pd.DataFrame | None, str | None]:
    """
    フォールバック + J-Quants優先ロジックで株価取得

    1. tachibana を試行
    2. tachibana 失敗時は stooq を試行
    3. 1 or 2 の成功に関わらず jquants も取得
    4. jquants のデータで上書き（同じ日付のレコードを置換）

    Returns:
        (DataFrame, source文字列) のタプル
    """
    base_df = None
    source = None

    # Step 1: Tachibana を試行
    try:
        base_df = sp._fetch_from_tachibana(code, from_, to)
        if base_df is not None and not base_df.empty:
            source = 'tachibana'
            logger.debug(f"  Tachibana: {len(base_df)} records")
    except Exception as e:
        logger.debug(f"  Tachibana failed: {e}")

    # Step 2: Tachibana 失敗時は Stooq を試行
    if base_df is None or base_df.empty:
        try:
            base_df = sp._fetch_from_stooq(code, from_, to)
            if base_df is not None and not base_df.empty:
                source = 'stooq'
                logger.debug(f"  Stooq: {len(base_df)} records")
        except Exception as e:
            logger.debug(f"  Stooq failed: {e}")

    # Step 3: J-Quants は常に取得し、上書き
    jquants_df = None
    try:
        jquants_df = sp._fetch_from_jquants(code, from_, to)
        if jquants_df is not None and not jquants_df.empty:
            logger.debug(f"  J-Quants: {len(jquants_df)} records")
    except Exception as e:
        logger.debug(f"  J-Quants failed: {e}")

    # Step 4: マージ（J-Quants優先）
    if jquants_df is not None and not jquants_df.empty:
        merged_df = merge_with_jquants_priority(base_df, jquants_df)
        final_source = 'jquants' if source is None else f'{source}+jquants'
        return merged_df, final_source

    return base_df, source


def upload_to_ftp(modified_codes: list[str], dry_run: bool = False) -> dict:
    """
    更新されたDuckDBファイルをFTPサーバーにアップロード

    Args:
        modified_codes: 更新された銘柄コードのリスト
        dry_run: Trueの場合、実際のアップロードをスキップ

    Returns:
        {'success': [...], 'failed': [...]}
    """
    from BackcastPro.api.ftp_client import FTPClient

    results = {'success': [], 'failed': []}

    if dry_run:
        logger.info("dry-run モード: FTPアップロードをスキップ")
        results['success'] = modified_codes
        return results

    if not modified_codes:
        logger.info("アップロード対象ファイルなし")
        return results

    client = FTPClient()
    if not client.config.is_configured():
        logger.error("FTP credentials not configured")
        for code in modified_codes:
            results['failed'].append((code, "FTP not configured"))
        return results

    cache_dir = os.environ.get('BACKCASTPRO_CACHE_DIR', '.')
    local_dir = os.path.join(cache_dir, 'stocks_daily')

    logger.info(f"FTP接続中: {client.config.host}:{client.config.port}")

    for code in modified_codes:
        local_path = os.path.join(local_dir, f"{code}.duckdb")

        if not os.path.exists(local_path):
            logger.warning(f"ローカルファイルなし: {local_path}")
            results['failed'].append((code, "File not found"))
            continue

        if client.upload_stocks_daily(code, local_path):
            results['success'].append(code)
            logger.debug(f"  アップロード完了: {code}.duckdb")
        else:
            results['failed'].append((code, "Upload failed"))

    logger.info("FTPアップロード処理完了")

    return results


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
        codes = [c.strip() for c in args.codes.split(',')]
        logger.info(f"指定銘柄: {codes}")
    else:
        codes = get_stock_codes_list()

    if not codes:
        logger.error("処理対象の銘柄がありません")
        return 1

    summary.total_stocks = len(codes)

    # 2. 日付範囲決定
    from_date, to_date = get_fetch_date_range(args.days)
    logger.info(f"取得期間: {from_date.strftime('%Y-%m-%d')} 〜 {to_date.strftime('%Y-%m-%d')}")

    # 3. 各銘柄の株価取得
    sp = stocks_price()
    modified_codes = []

    for i, code in enumerate(codes, 1):
        logger.info(f"[{i}/{len(codes)}] {code} 処理中...")
        try:
            df, source = fetch_and_merge_stock_price(sp, code, from_date, to_date)
            if df is not None and not df.empty:
                sp.db.save_stock_prices(code, df)
                modified_codes.append(code)
                summary.success_count += 1
                logger.info(f"  → 成功 (source: {source}, records: {len(df)})")
            else:
                summary.failed_count += 1
                summary.errors.append((code, "No data returned"))
                logger.warning(f"  → データなし")
        except Exception as e:
            summary.failed_count += 1
            summary.errors.append((code, str(e)))
            logger.error(f"  → 失敗: {e}")

    # 4. FTPアップロード
    logger.info("-" * 50)
    logger.info(f"FTPアップロード開始: {len(modified_codes)} ファイル")
    ftp_results = upload_to_ftp(modified_codes, dry_run=args.dry_run)
    summary.ftp_uploaded = len(ftp_results['success'])
    summary.ftp_failed = len(ftp_results['failed'])

    # 5. サマリー出力
    summary.end_time = datetime.now()
    duration = summary.end_time - summary.start_time

    logger.info("=" * 50)
    logger.info("処理完了サマリー")
    logger.info("=" * 50)
    logger.info(f"処理時間: {duration}")
    logger.info(f"対象銘柄: {summary.total_stocks}")
    logger.info(f"成功: {summary.success_count}")
    logger.info(f"失敗: {summary.failed_count}")
    logger.info(f"FTPアップロード: 成功={summary.ftp_uploaded}, 失敗={summary.ftp_failed}")

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