"""
BackcastPro をご利用いただきありがとうございます。

インストール後のご案内（インストール済みユーザー向け）

- ドキュメント総合トップ: [index.md](https://github.com/botterYosuke/BackcastPro/blob/main/docs/index.md)
- クイックスタート/チュートリアル: [tutorial.md](https://github.com/botterYosuke/BackcastPro/blob/main/docs/tutorial.md)
- APIリファレンス: [BackcastPro - APIリファレンス](https://botteryosuke.github.io/BackcastPro/namespacesrc_1_1BackcastPro.html)
- トラブルシューティング: [troubleshooting.md](https://github.com/botterYosuke/BackcastPro/blob/main/docs/troubleshooting.md)

※ 使い始めはチュートリアル → 詳細はAPIリファレンスをご参照ください。
"""
from .backtest import Backtest

from .api.stocks_price import get_stock_daily
from .api.stocks_board import get_stock_board
from .api.stocks_info import get_stock_info
from .api.chart import chart, chart_by_df
from .api.board import board

__all__ = [
    'Backtest',
    'get_stock_daily',
    'get_stock_board',
    'get_stock_info',
    'chart',
    'chart_by_df',
    'board'
]
