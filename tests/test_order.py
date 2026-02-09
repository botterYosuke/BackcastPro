"""
注文管理モジュール (order.py) のテスト

Order/Trade/Positionは _Broker に依存するため、
Backtest経由の統合テストで各プロパティを検証する。
"""

import numpy as np
import pandas as pd
import pytest

from BackcastPro import Backtest


def _create_bt(days=20, cash=100000):
    """テスト用Backtestインスタンスを生成"""
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    np.random.seed(42)
    base = 1000
    returns = np.random.randn(days) * 0.02
    prices = base * np.cumprod(1 + returns)
    df = pd.DataFrame(
        {
            "Open": prices * (1 + np.random.randn(days) * 0.003),
            "High": prices * (1 + np.abs(np.random.randn(days) * 0.01)),
            "Low": prices * (1 - np.abs(np.random.randn(days) * 0.01)),
            "Close": prices,
            "Volume": np.random.randint(1000, 10000, days),
        },
        index=dates,
    )
    bt = Backtest(data={"TEST": df}, cash=cash)
    return bt


class TestOrderProperties:
    """Order のプロパティテスト"""

    def test_order_created_by_buy(self):
        """buy()で注文が生成される"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        assert len(bt.orders) == 1

    def test_order_code(self):
        """Order.code が正しい"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        order = bt.orders[0]
        assert order.code == "TEST"

    def test_order_size_long(self):
        """ロング注文のサイズが正"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        order = bt.orders[0]
        assert order.size == 10
        assert order.is_long is True
        assert order.is_short is False

    def test_order_size_short(self):
        """ショート注文のサイズが負"""
        bt = _create_bt()
        bt.goto(5)
        bt.sell(code="TEST", size=10)
        order = bt.orders[0]
        assert order.size == -10
        assert order.is_short is True
        assert order.is_long is False

    def test_order_limit_price(self):
        """指値注文の指値価格"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10, limit=950.0)
        order = bt.orders[0]
        assert order.limit == 950.0

    def test_order_stop_price(self):
        """ストップ注文のストップ価格"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10, stop=1050.0)
        order = bt.orders[0]
        assert order.stop == 1050.0

    def test_order_market_no_limit_no_stop(self):
        """成行注文はlimit/stopがNone"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        order = bt.orders[0]
        assert order.limit is None
        assert order.stop is None

    def test_order_sl_tp(self):
        """SL/TP付き注文"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10, sl=900.0, tp=1200.0)
        order = bt.orders[0]
        assert order.sl == 900.0
        assert order.tp == 1200.0

    def test_order_tag(self):
        """注文タグ"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10, tag="entry_signal")
        order = bt.orders[0]
        assert order.tag == "entry_signal"

    def test_order_cancel(self):
        """注文のキャンセル"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        assert len(bt.orders) == 1
        bt.orders[0].cancel()
        assert len(bt.orders) == 0

    def test_order_is_contingent_false_for_standalone(self):
        """単独注文はis_contingent=False"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        order = bt.orders[0]
        assert order.is_contingent is False

    def test_order_executed_creates_trade(self):
        """注文が約定するとTradeが生成される"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        assert len(bt.orders) == 1
        bt.step()
        assert len(bt.orders) == 0
        assert len(bt.trades) == 1
