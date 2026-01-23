"""
過去の約定情報（equities_trades）をDuckDBに保存するスクリプト

Usage:
    python import_equities_trades.py                    # 全ファイルを処理
    python import_equities_trades.py --code 3823        # 特定銘柄のみ
    python import_equities_trades.py --file equities_trades_202401.csv.gz  # 特定ファイルのみ
"""

import os
import sys
import glob
import duckdb
import pandas as pd
import argparse
import logging
from datetime import datetime
from typing import Optional, List

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# パス設定
JQUANTS_DIR = r"S:\j-quants"
OUTPUT_DIR = r"S:\jp\stocks_trades"


def ensure_table(db: duckdb.DuckDBPyConnection, table_name: str = "stocks_trades") -> None:
    """テーブルが存在しない場合は作成"""
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        "Price" DOUBLE,
        "Qty" BIGINT,
        "Type" VARCHAR(20),
        "TransactionId" BIGINT NOT NULL,
        "source" VARCHAR(50),
        "Code" VARCHAR(10) NOT NULL,
        "Timestamp" VARCHAR(30) NOT NULL,
        "created_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        "updated_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY ("Code", "TransactionId")
    )
    """
    db.execute(create_sql)
    db.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_Code ON {table_name}("Code")')
    db.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_Timestamp ON {table_name}("Timestamp")')


def ensure_metadata_table(db: duckdb.DuckDBPyConnection) -> None:
    """メタデータテーブルが存在しない場合は作成"""
    create_sql = """
    CREATE TABLE IF NOT EXISTS stocks_trades_metadata (
        "Code" VARCHAR(10) PRIMARY KEY,
        "from_timestamp" TIMESTAMP,
        "to_timestamp" TIMESTAMP,
        "record_count" INTEGER,
        "last_updated" TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    db.execute(create_sql)


def update_metadata(db: duckdb.DuckDBPyConnection, code: str) -> None:
    """メタデータを更新"""
    ensure_metadata_table(db)

    # 現在のデータ範囲を取得
    stats = db.execute("""
        SELECT MIN("Timestamp") as min_ts, MAX("Timestamp") as max_ts, COUNT(*) as count
        FROM stocks_trades WHERE "Code" = ?
    """, [code]).fetchone()

    if stats and stats[0]:
        # 既存レコードを確認
        existing = db.execute(
            'SELECT "from_timestamp", "to_timestamp" FROM stocks_trades_metadata WHERE "Code" = ?',
            [code]
        ).fetchone()

        if existing:
            # 既存データがある場合は期間を拡張して更新
            new_from = min(str(stats[0]), str(existing[0])) if existing[0] else str(stats[0])
            new_to = max(str(stats[1]), str(existing[1])) if existing[1] else str(stats[1])
            db.execute("""
                UPDATE stocks_trades_metadata
                SET "from_timestamp" = ?, "to_timestamp" = ?, "record_count" = ?, "last_updated" = CURRENT_TIMESTAMP
                WHERE "Code" = ?
            """, [new_from, new_to, stats[2], code])
        else:
            # 新規挿入
            db.execute("""
                INSERT INTO stocks_trades_metadata ("Code", "from_timestamp", "to_timestamp", "record_count")
                VALUES (?, ?, ?, ?)
            """, [code, stats[0], stats[1], stats[2]])


def process_csv_file(csv_path: str, target_codes: Optional[List[str]] = None) -> dict:
    """
    CSVファイルを処理して銘柄ごとにDuckDBに保存

    Args:
        csv_path: CSVファイルパス
        target_codes: 処理対象の銘柄コードリスト（Noneの場合は全銘柄）

    Returns:
        処理結果の統計情報
    """
    logger.info(f"処理開始: {os.path.basename(csv_path)}")

    # CSVを読み込み
    df = pd.read_csv(csv_path, compression='gzip', dtype={'Code': str})
    logger.info(f"読み込み完了: {len(df)} 件")

    # Codeを4文字にする
    df['Code'] = df['Code'].str[:4]

    # 対象銘柄でフィルタリング
    if target_codes:
        df = df[df['Code'].isin(target_codes)]
        logger.info(f"対象銘柄フィルタリング後: {len(df)} 件")

    if df.empty:
        logger.info("処理対象データがありません")
        return {'processed': 0, 'codes': []}

    # Timestampカラムを作成 (Date + Time)
    df['Timestamp'] = df['Date'] + ' ' + df['Time']

    # カラム名のマッピング
    df = df.rename(columns={
        'TradingVolume': 'Qty',
        'SessionDistinction': 'Type'
    })

    # sourceを追加
    df['source'] = 'j-quants'

    # 必要なカラムのみ抽出（TransactionIdを含める）
    df = df[['Price', 'Qty', 'Type', 'TransactionId', 'source', 'Code', 'Timestamp']]

    # 銘柄コードごとにグループ化して処理
    stats = {'processed': 0, 'codes': []}

    for code, group_df in df.groupby('Code'):
        db_path = os.path.join(OUTPUT_DIR, f"{code}.duckdb")
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        try:
            db = duckdb.connect(db_path)
            db.execute("BEGIN TRANSACTION")

            try:
                ensure_table(db)

                # 既存のTransactionIdを取得
                existing_ids = set()
                try:
                    result = db.execute('SELECT DISTINCT "TransactionId" FROM stocks_trades WHERE "Code" = ?', [code]).fetchall()
                    existing_ids = {row[0] for row in result}
                except:
                    pass

                # 新規データのみフィルタリング
                new_df = group_df[~group_df['TransactionId'].isin(existing_ids)]

                if not new_df.empty:
                    # バッチ挿入
                    db.register('temp_df', new_df)
                    db.execute("""
                        INSERT INTO stocks_trades ("Price", "Qty", "Type", "TransactionId", "source", "Code", "Timestamp")
                        SELECT "Price", "Qty", "Type", "TransactionId", "source", "Code", "Timestamp" FROM temp_df
                    """)

                    # メタデータ更新
                    update_metadata(db, code)

                    logger.info(f"  {code}: {len(new_df)} 件追加（重複 {len(group_df) - len(new_df)} 件スキップ）")
                    stats['processed'] += len(new_df)
                    stats['codes'].append(code)
                else:
                    logger.debug(f"  {code}: 新規データなし")

                db.execute("COMMIT")

            except Exception as e:
                db.execute("ROLLBACK")
                raise e
            finally:
                db.close()

        except Exception as e:
            logger.error(f"  {code}: エラー - {e}")

    return stats


def main():
    parser = argparse.ArgumentParser(description='過去の約定情報をDuckDBに保存')
    parser.add_argument('--code', type=str, help='特定の銘柄コードのみ処理')
    parser.add_argument('--file', type=str, help='特定のファイルのみ処理')
    parser.add_argument('--dry-run', action='store_true', help='実際には保存せずに処理内容を表示')
    args = parser.parse_args()

    # 対象ファイルを取得
    if args.file:
        csv_files = [os.path.join(JQUANTS_DIR, args.file)]
    else:
        csv_files = sorted(glob.glob(os.path.join(JQUANTS_DIR, "equities_trades_*.csv.gz")))

    if not csv_files:
        logger.error("処理対象のファイルが見つかりません")
        sys.exit(1)

    logger.info(f"処理対象ファイル: {len(csv_files)} 件")

    # 対象銘柄
    target_codes = [args.code] if args.code else None

    # 全体の統計
    total_stats = {'processed': 0, 'codes': set()}

    for csv_file in csv_files:
        if not os.path.exists(csv_file):
            logger.warning(f"ファイルが見つかりません: {csv_file}")
            continue

        stats = process_csv_file(csv_file, target_codes)
        total_stats['processed'] += stats['processed']
        total_stats['codes'].update(stats['codes'])

    logger.info("=" * 50)
    logger.info(f"処理完了: {total_stats['processed']} 件, {len(total_stats['codes'])} 銘柄")


if __name__ == "__main__":
    main()
