import sys
from pathlib import Path

# Add src to python path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path.resolve()))

from trading_data.stocks_info import get_stock_info

if __name__ == "__main__":
    try:
        df = get_stock_info()
        print("Success:")
        print(df.head())
    except Exception as e:
        import traceback

        traceback.print_exc()
