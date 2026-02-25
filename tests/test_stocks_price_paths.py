import os
import sys
from dotenv import load_dotenv

# プロジェクトルートにパスを通す
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, "src"))

# .envを読み込む
load_dotenv(override=True)

from trading_data.stocks_price import stocks_price, get_stock_minute
from BackcastPro.api.db_stocks_daily import db_stocks_daily


def test_daily_path():
    print("=== Testing db_stocks_daily path ===")
    print(f"ENV: STOCKDATA_CACHE_DIR = {os.environ.get('STOCKDATA_CACHE_DIR')}")
    db_daily = db_stocks_daily()
    path = db_daily._get_db_path("7203")
    print(f"db_stocks_daily('7203') path: {path}")
    expected = os.path.join(
        os.environ.get("STOCKDATA_CACHE_DIR", ""), "jp", "stocks_daily", "7203.duckdb"
    )
    expected_alt = os.path.join(
        os.environ.get("STOCKDATA_CACHE_DIR", ""), "jp/stocks_daily", "7203.duckdb"
    )
    if os.path.normpath(path) == os.path.normpath(expected) or os.path.normpath(
        path
    ) == os.path.normpath(expected_alt):
        print("-> SUCCESS: The daily path uses S:\\jp\\stocks_daily\\")
    else:
        print("-> FAILED: Path does not match expected S:\\jp\\stocks_daily\\")


def test_minute_path():
    print("\n=== Testing get_stock_minute path ===")
    try:
        # この関数は内部でS:\\jp\\stocks_minute\\[code].duckdb を直接参照している
        # DBが存在しない場合はエラーになるので、それをキャッチしてパスを確認する。
        get_stock_minute("7203")
    except ValueError as e:
        msg = str(e)
        print(f"Exception message: {msg}")
        if "S:\\jp\\stocks_minute\\7203.duckdb" in msg:
            print("-> SUCCESS: The minute function accesses S:\\jp\\stocks_minute\\")
        else:
            print("-> FAILED: Could not confirm the minute path from the error.")
    except Exception as e:
        print(f"Unexpected Exception: {type(e).__name__}: {str(e)}")


if __name__ == "__main__":
    test_daily_path()
    test_minute_path()
