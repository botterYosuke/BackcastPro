"""
ポジション管理モジュール。
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._broker import _Broker


class Position:
    """
    現在保有している資産ポジション。
    `backtesting.backtesting.Strategy.next`内で
    `backtesting.backtesting.Strategy.position`として利用可能です。
    ブール値コンテキストで使用できます。例：

        if self.position:
            ...  # ポジションがあります（ロングまたはショート）
    """
    
    def __init__(self, broker: '_Broker'):
        self.__broker = broker

    def __bool__(self):
        return self.size != 0

    @property
    def size(self) -> float:
        """資産単位でのポジションサイズ。ショートポジションの場合は負の値。"""
        return sum(trade.size for trade in self.__broker.trades)

    @property
    def pl(self) -> float:
        """現在のポジションの利益（正）または損失（負）を現金単位で。"""
        return sum(trade.pl for trade in self.__broker.trades)

    @property
    def pl_pct(self) -> float:
        """現在のポジションの利益（正）または損失（負）をパーセントで。"""
        total_invested = sum(trade.entry_price * abs(trade.size) for trade in self.__broker.trades)
        return (self.pl / total_invested) * 100 if total_invested else 0

    @property
    def is_long(self) -> bool:
        """ポジションがロング（ポジションサイズが正）の場合True。"""
        return self.size > 0

    @property
    def is_short(self) -> bool:
        """ポジションがショート（ポジションサイズが負）の場合True。"""
        return self.size < 0

    def close(self, portion: float = 1.):
        """
        各アクティブな取引の「一部」を決済することで、ポジションの一部を決済します。詳細は「Trade.close」を参照してください。
        """
        for trade in self.__broker.trades:
            trade.close(portion)

