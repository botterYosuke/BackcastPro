"""mother.duckdb → 個別DB 分割のみ実行"""

import os
import sys
import logging
from dotenv import load_dotenv

# .env を読み込む
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
os.environ["STOCKDATA_CACHE_DIR"] = os.path.abspath(
    os.environ.get("STOCKDATA_CACHE_DIR", "/cache")
)

from trading_data.stocks_price import stocks_price
from BackcastPro.api.db_stocks_daily_mother import db_stocks_daily_mother

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    sp = stocks_price()
    mother_db = db_stocks_daily_mother()

    logger.info("mother.duckdb → 個別DB 分割開始...")
    split_result = mother_db.split_to_individual(sp.db)
    logger.info(
        f"split完了: 成功={split_result['success']}, 失敗={split_result['failed']}"
    )
    if split_result["errors"]:
        logger.info(f"エラー銘柄: {split_result['errors'][:10]}")
        if len(split_result["errors"]) > 10:
            logger.info(f"  ... 他 {len(split_result['errors']) - 10} 件")

    return 0 if split_result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
