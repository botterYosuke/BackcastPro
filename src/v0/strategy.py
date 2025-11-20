"""
トレーディング戦略の基底クラス。
"""

from __future__ import annotations

import sys
from abc import ABCMeta, abstractmethod
from tkinter import NO
from typing import Optional, Tuple

import pandas as pd

# Import classes from their new modules
from .order import Order
from .position import Position
from .trade import Trade
from ._broker import _Broker

# pdoc（Pythonドキュメント生成ツール）の設定
# Falseを設定することで、該当するメソッドをドキュメントから除外
# 通常、__init__メソッドは内部実装の詳細であり、ユーザー向けドキュメントには不要
__pdoc__ = {
    'Strategy.__init__': False,
    'Order.__init__': False,
    'Position.__init__': False,
    'Trade.__init__': False,
}


class Strategy(metaclass=ABCMeta):
    """
    トレーディング戦略の基底クラス。このクラスを拡張し、
    `backtesting.backtesting.Strategy.init` と
    `backtesting.backtesting.Strategy.next` メソッドを
    オーバーライドして独自の戦略を定義してください。
    """
    
    def __init__(self, broker: _Broker, data: dict[str, pd.DataFrame]):
        """
        これは Backtestクラスで初期化するためユーザーは不要
        """
        self._broker: _Broker = broker
        self._data: dict[str, pd.DataFrame] = data


    @abstractmethod
    def init(self):
        """
        戦略を初期化します。
        このメソッドをオーバーライドしてください。
        戦略開始前に、事前計算が必要なものやベクトル化された方法で
        事前計算できるものを事前計算します。

        `backtesting.lib`からコンポーザブル戦略を拡張する場合は、
        必ず以下を呼び出してください：

            super().init()
        """

    @abstractmethod
    def next(self, current_time: pd.Timestamp):
        """
        メインのストラテジー実行メソッド。新しい
        `backtesting.backtesting.Strategy.data`
        インスタンス（行；完全なローソク足バー）が利用可能になるたびに呼び出されます。
        これは、`backtesting.backtesting.Strategy.init`で
        事前計算されたデータに基づくストラテジーの意思決定が
        行われるメインメソッドです。

        `backtesting.lib`からコンポーザブルストラテジーを拡張する場合は、
        必ず以下を呼び出してください：

            super().next()
        """
        

    class __FULL_EQUITY(float):  # noqa: N801
        """
        利用可能資金のほぼ100%を表す特別な浮動小数点数クラス。
        floatを継承し、表示時に'.9999'として表示される。
        浮動小数点の精度問題を回避し、安全な取引を可能にする。
        """
        def __repr__(self): return '.9999'  # noqa: E704

    # 利用可能資金のほぼ100%を使用するための特別な値
    # 1 - sys.float_info.epsilonにより、浮動小数点の精度問題を回避し、
    # 手数料やスプレッドを考慮した安全な取引を可能にする
    _FULL_EQUITY = __FULL_EQUITY(1 - sys.float_info.epsilon)

    def buy(self, *,
            code: str,
            size: float = _FULL_EQUITY,
            limit: Optional[float] = None,
            stop: Optional[float] = None,
            sl: Optional[float] = None,
            tp: Optional[float] = None,
            tag: object = None) -> 'Order':
        """
        新しいロングオーダーを発注し、それを返します。パラメータの説明については、
        `Order` とそのプロパティを参照してください。
        `Backtest(..., trade_on_close=True)` で実行していない限り、
        成行注文は次のバーの始値で約定され、
        その他の注文タイプ（指値、ストップ指値、ストップ成行）は
        それぞれの条件が満たされたときに約定されます。

        既存のポジションをクローズするには、`Position.close()` と `Trade.close()` を参照してください。

        `Strategy.sell()` も参照してください。
        """
        assert 0 < size < 1 or round(size) == size >= 1, \
            "sizeは正の資産割合または正の整数単位である必要があります"

        return self._broker.new_order(code, size, limit, stop, sl, tp, tag)

    def sell(self, *,
             code: str,
             size: float = _FULL_EQUITY,
             limit: Optional[float] = None,
             stop: Optional[float] = None,
             sl: Optional[float] = None,
             tp: Optional[float] = None,
             tag: object = None) -> 'Order':
        """
        新しいショートオーダーを発注し、それを返します。パラメータの説明については、
        `Order` とそのプロパティを参照してください。

        .. caution::
            `self.sell(size=.1)` は、以下の場合を除いて、
            既存の `self.buy(size=.1)` トレードをクローズしないことに注意してください：

            * バックテストが `exclusive_orders=True` で実行された場合、
            * 両方のケースで原資産価格が等しく、
              バックテストが `spread = commission = 0` で実行された場合。

            トレードを明示的に終了するには、`Trade.close()` または `Position.close()` を使用してください。

        `Strategy.buy()` も参照してください。

        .. note::
            既存のロングポジションをクローズしたいだけの場合は、
            `Position.close()` または `Trade.close()` を使用してください。
        """
        assert 0 < size < 1 or round(size) == size >= 1, \
            "sizeは正の資産割合または正の整数単位である必要があります"

        return self._broker.new_order(code, -size, limit, stop, sl, tp, tag)

    @property
    def equity(self) -> float:
        """現在のアカウント資産（現金プラス資産）。"""
        return self._broker.equity

    @property
    def data(self) -> dict[str, pd.DataFrame]:
        """
        価格データは、`Backtest.__init__`に渡されるものと同じ
        """
        return self._data

    @property
    def position(self) -> 'Position':
        """`Position` のインスタンス。"""
        return self._broker.position

    @property
    def orders(self) -> 'Tuple[Order, ...]':
        """実行待ちのオーダーリスト（`Order` を参照）。"""
        return tuple(self._broker.orders)

    @property
    def trades(self) -> 'Tuple[Trade, ...]':
        """アクティブなトレードリスト（`Trade` を参照）。"""
        return tuple(self._broker.trades)

    @property
    def closed_trades(self) -> 'Tuple[Trade, ...]':
        """決済済みトレードリスト（`Trade` を参照）。"""
        return tuple(self._broker.closed_trades)

