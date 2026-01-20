"""
get_stock_board関数のデバッグ用スクリプト
"""

from BackcastPro.api.api_stocks import get_stock_board

# デバッグしたい銘柄コードを指定
code = "7203"  # トヨタ自動車の例

# ここにブレークポイントを設定してデバッグ
result = get_stock_board(code)

print(result)
