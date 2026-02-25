import logging
import time
import os
import sys

# プロジェクトルートのsrcにパスを通す
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, "src"))

from trading_data.stocks_info import get_stock_info
from BackcastPro.api.db_stocks_info import db_stocks_info

logging.basicConfig(level=logging.DEBUG)


def main():
    print("Testing get_stock_info('7203')")
    try:
        df = get_stock_info("7203")
        print(f"Dataframe received: {df.shape if df is not None else None}")

        # db_stocks_infoのスレッドが終了するのを待つ
        print("Waiting for background thread to finish...")
        time.sleep(5)
    except Exception as e:
        import traceback

        traceback.print_exc()

    print("Done")


if __name__ == "__main__":
    main()
