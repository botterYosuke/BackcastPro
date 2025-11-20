"""
注文管理モジュール。
"""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ._broker import _Broker
    from .trade import Trade


class Order:
    """
    `Strategy.buy()`と`Strategy.sell()`を通じて新しい注文を出します。
    `Strategy.orders`を通じて既存の注文を照会します。

    注文が実行または[約定]されると、`Trade`が発生します。

    出されたがまだ約定されていない注文の側面を変更したい場合は、
    キャンセルして新しい注文を出してください。

    すべての出された注文は[取消注文まで有効]です。
    """
    
    def __init__(self, broker: '_Broker',
                 code: str,
                 size: float,
                 limit_price: Optional[float] = None,
                 stop_price: Optional[float] = None,
                 sl_price: Optional[float] = None,
                 tp_price: Optional[float] = None,
                 parent_trade: Optional['Trade'] = None,
                 tag: object = None):
        self.__code = code
        self.__broker = broker
        assert size != 0
        self.__size = size
        self.__limit_price = limit_price
        self.__stop_price = stop_price
        self.__sl_price = sl_price
        self.__tp_price = tp_price
        self.__parent_trade = parent_trade
        self.__tag = tag

    def _replace(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, f'_{self.__class__.__qualname__}__{k}', v)
        return self


    def cancel(self):
        """注文をキャンセルします。"""
        self.__broker.orders.remove(self)
        trade = self.__parent_trade
        if trade:
            if self is trade._sl_order:
                trade._replace(sl_order=None)
            elif self is trade._tp_order:
                trade._replace(tp_order=None)
            else:
                pass  # Order placed by Trade.close()

    # Fields getters

    @property
    def code(self) -> str:
        """
        注文対象の銘柄コード。
        """
        return self.__code

    @property
    def size(self) -> float:
        """
        注文サイズ（ショート注文の場合は負の値）。

        サイズが0と1の間の値の場合、現在利用可能な流動性（現金 + `Position.pl` - 使用済みマージン）の
        割合として解釈されます。
        1以上の値は絶対的なユニット数を示します。
        """
        return self.__size

    @property
    def limit(self) -> Optional[float]:
        """
        [指値注文]の注文指値価格、または[成行注文]の場合はNone（次に利用可能な価格で約定）。

        [limit orders]: https://www.investopedia.com/terms/l/limitorder.asp
        [market orders]: https://www.investopedia.com/terms/m/marketorder.asp
        """
        return self.__limit_price

    @property
    def stop(self) -> Optional[float]:
        """
        [ストップリミット/ストップ成行]注文の注文ストップ価格。
        ストップが設定されていない場合、またはストップ価格が既にヒットした場合はNone。

        [_]: https://www.investopedia.com/terms/s/stoporder.asp
        """
        return self.__stop_price

    @property
    def sl(self) -> Optional[float]:
        """
        ストップロス価格。設定されている場合、この注文の実行後に`Trade`に対して
        新しい条件付きストップ成行注文が配置されます。
        `Trade.sl`も参照してください。
        """
        return self.__sl_price

    @property
    def tp(self) -> Optional[float]:
        """
        テイクプロフィット価格。設定されている場合、この注文の実行後に`Trade`に対して
        新しい条件付き指値注文が配置されます。
        `Trade.tp`も参照してください。
        """
        return self.__tp_price

    @property
    def parent_trade(self):
        return self.__parent_trade

    @property
    def tag(self):
        """
        任意の値（文字列など）。設定されている場合、この注文と関連する`Trade`の
        追跡が可能になります（`Trade.tag`を参照）。
        """
        return self.__tag

    __pdoc__ = {'Order.parent_trade': False}

    # Extra properties

    @property
    def is_long(self):
        """注文がロングの場合（注文サイズが正）にTrueを返します。"""
        return self.__size > 0

    @property
    def is_short(self):
        """注文がショートの場合（注文サイズが負）にTrueを返します。"""
        return self.__size < 0

    @property
    def is_contingent(self):
        """
        [条件付き]注文、つまりアクティブな取引に配置された[OCO]ストップロスおよび
        テイクプロフィットブラケット注文の場合にTrueを返します。
        親`Trade`がクローズされると、残りの条件付き注文はキャンセルされます。

        `Trade.sl`と`Trade.tp`を通じて条件付き注文を変更できます。

        [contingent]: https://www.investopedia.com/terms/c/contingentorder.asp
        [OCO]: https://www.investopedia.com/terms/o/oco.asp
        """
        return bool((parent := self.__parent_trade) and
                    (self is parent._sl_order or
                     self is parent._tp_order))
