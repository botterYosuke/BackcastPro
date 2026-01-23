"""
過去の分足情報をDuckDBデータベースに保存するスクリプト

CSVファイル: S:/j-quants/equities_bars_minute_*.csv.gz
出力先: S:/jp/stocks_minute/{code}.duckdb
"""

import os
import glob
import gzip
import pandas as pd
import duckdb
from datetime import datetime
import logging
from typing import List, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 設定
CSV_DIR = "S:/j-quants"
CSV_PATTERN = "equities_bars_minute_*.csv.gz"
DB_DIR = "S:/jp/stocks_minute"
TABLE_NAME = "stocks_minute"


def get_db_path(code: str) -> str:
    """銘柄コードからDBパスを取得"""
    return os.path.join(DB_DIR, f"{code}.duckdb")


def ensure_table(db: duckdb.DuckDBPyConnection) -> None:
    """分足テーブルを作成（存在しない場合）"""
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        "Date" DATE,
        "Time" VARCHAR(10),
        "Code" VARCHAR(20),
        "Open" DOUBLE,
        "High" DOUBLE,
        "Low" DOUBLE,
        "Close" DOUBLE,
        "Volume" BIGINT,
        "Value" BIGINT,
        "created_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY ("Date", "Time", "Code")
    )
    """
    db.execute(create_sql)


def ensure_metadata_table(db: duckdb.DuckDBPyConnection) -> None:
    """メタデータテーブルを作成（存在しない場合）"""
    create_sql = """
    CREATE TABLE IF NOT EXISTS stocks_minute_metadata (
        "Code" VARCHAR(20) PRIMARY KEY,
        "from_date" DATE,
        "to_date" DATE,
        "record_count" INTEGER,
        "last_updated" TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    db.execute(create_sql)


def save_metadata(db: duckdb.DuckDBPyConnection, code: str) -> None:
    """メタデータを保存/更新"""
    ensure_metadata_table(db)

    stats = db.execute(f"""
        SELECT MIN("Date"), MAX("Date"), COUNT(*)
        FROM {TABLE_NAME}
        WHERE "Code" = ?
    """, [code]).fetchone()

    if stats and stats[0]:
        from_date, to_date, count = stats
        db.execute("""
            INSERT OR REPLACE INTO stocks_minute_metadata
            ("Code", "from_date", "to_date", "record_count", "last_updated")
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, [code, from_date, to_date, count])
        logger.info(f"メタデータ更新: {code} ({from_date} ~ {to_date}, {count}件)")


def process_csv_file(csv_path: str, target_codes: Optional[List[str]] = None) -> dict:
    """
    CSVファイルを処理してデータベースに保存

    Args:
        csv_path: CSVファイルパス
        target_codes: 処理対象の銘柄コードリスト（Noneの場合は全銘柄）

    Returns:
        処理結果の辞書 {code: record_count}
    """
    logger.info(f"処理開始: {os.path.basename(csv_path)}")

    # gzip圧縮されたCSVを読み込み
    df = pd.read_csv(csv_path, compression='gzip', dtype={
        'Date': str,
        'Time': str,
        'Code': str,
        'O': float,
        'H': float,
        'L': float,
        'C': float,
        'Vo': 'Int64',
        'Va': 'Int64'
    })

    # Codeを4文字にする
    df['Code'] = df['Code'].str[:4]

    # カラム名をリネーム
    df = df.rename(columns={
        'O': 'Open',
        'H': 'High',
        'L': 'Low',
        'C': 'Close',
        'Vo': 'Volume',
        'Va': 'Value'
    })

    # Dateをdatetime型に変換
    df['Date'] = pd.to_datetime(df['Date']).dt.date

    # 対象銘柄でフィルタリング
    if target_codes:
        df = df[df['Code'].isin(target_codes)]

    if df.empty:
        logger.info(f"対象データなし: {os.path.basename(csv_path)}")
        return {}

    # 銘柄ごとにグループ化して処理
    results = {}
    grouped = df.groupby('Code')

    for code, group_df in grouped:
        db_path = get_db_path(code)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        db = duckdb.connect(db_path)
        try:
            ensure_table(db)

            db.execute("BEGIN TRANSACTION")
            try:
                # 既存データとの重複を除外
                existing = db.execute(f"""
                    SELECT DISTINCT "Date", "Time" FROM {TABLE_NAME} WHERE "Code" = ?
                """, [code]).fetchdf()

                if not existing.empty:
                    existing['Date'] = pd.to_datetime(existing['Date']).dt.date
                    existing_keys = set(zip(existing['Date'], existing['Time']))

                    group_df = group_df[~group_df.apply(
                        lambda row: (row['Date'], row['Time']) in existing_keys,
                        axis=1
                    )]

                if not group_df.empty:
                    # データを挿入
                    db.register('temp_df', group_df)
                    db.execute(f"""
                        INSERT INTO {TABLE_NAME}
                        ("Date", "Time", "Code", "Open", "High", "Low", "Close", "Volume", "Value")
                        SELECT "Date", "Time", "Code", "Open", "High", "Low", "Close", "Volume", "Value"
                        FROM temp_df
                    """)
                    results[code] = len(group_df)
                    logger.debug(f"  {code}: {len(group_df)}件追加")

                # メタデータ更新
                save_metadata(db, code)

                db.execute("COMMIT")
            except Exception as e:
                db.execute("ROLLBACK")
                raise e
        finally:
            db.close()

    logger.info(f"処理完了: {os.path.basename(csv_path)} - {len(results)}銘柄, {sum(results.values())}件")
    return results


def import_all_minute_bars(target_codes: Optional[List[str]] = None,
                           start_date: Optional[str] = None,
                           end_date: Optional[str] = None) -> None:
    """
    全ての分足CSVファイルをインポート

    Args:
        target_codes: 処理対象の銘柄コードリスト（Noneの場合は全銘柄）
        start_date: 開始年月 (例: "202401")
        end_date: 終了年月 (例: "202412")
    """
    csv_files = sorted(glob.glob(os.path.join(CSV_DIR, CSV_PATTERN)))

    if not csv_files:
        logger.error(f"CSVファイルが見つかりません: {os.path.join(CSV_DIR, CSV_PATTERN)}")
        return

    # 日付範囲でフィルタリング
    if start_date or end_date:
        filtered_files = []
        for f in csv_files:
            # ファイル名から日付部分を抽出 (equities_bars_minute_YYYYMM.csv.gz)
            basename = os.path.basename(f)
            date_part = basename.replace("equities_bars_minute_", "").replace(".csv.gz", "")

            if start_date and date_part < start_date:
                continue
            if end_date and date_part > end_date:
                continue
            filtered_files.append(f)
        csv_files = filtered_files

    logger.info(f"処理対象ファイル数: {len(csv_files)}")

    total_results = {}
    errors = []
    for csv_file in csv_files:
        try:
            results = process_csv_file(csv_file, target_codes)
            for code, count in results.items():
                total_results[code] = total_results.get(code, 0) + count
        except Exception as e:
            logger.error(f"ファイル処理エラー: {os.path.basename(csv_file)} - {e}")
            errors.append((csv_file, str(e)))

    logger.info(f"インポート完了: {len(total_results)}銘柄, 合計{sum(total_results.values())}件")
    if errors:
        logger.warning(f"エラーが発生したファイル: {len(errors)}件")


def import_single_stock(code: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> None:
    """
    単一銘柄の分足データをインポート

    Args:
        code: 銘柄コード
        start_date: 開始年月 (例: "202401")
        end_date: 終了年月 (例: "202412")
    """
    import_all_minute_bars(target_codes=[code], start_date=start_date, end_date=end_date)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="分足データをDuckDBにインポート")
    parser.add_argument("--codes", nargs="*", help="処理対象の銘柄コード（省略時は全銘柄）")
    parser.add_argument("--start", help="開始年月 (例: 202401)")
    parser.add_argument("--end", help="終了年月 (例: 202412)")
    parser.add_argument("--single", help="単一銘柄のインポート")

    args = parser.parse_args()

    if args.single:
        import_single_stock(args.single, start_date=args.start, end_date=args.end)
    else:
        import_all_minute_bars(
            target_codes=args.codes,
            start_date=args.start,
            end_date=args.end
        )
