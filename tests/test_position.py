"""
ポジション管理モジュール (position.py) のテスト
"""

import numpy as np
import pandas as pd
import pytest

from BackcastPro import Backtest


def _create_bt(days=30, cash=1000000):
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


class TestPositionBeforeStart:
    """未開始状態での Position テスト"""

    def test_position_before_start_is_falsy(self):
        """未開始状態のポジションはFalse"""
        bt = _create_bt()
        assert not bt.position

    def test_position_before_start_size_zero(self):
        """未開始状態のポジションサイズは0"""
        bt = _create_bt()
        assert bt.position.size == 0

    def test_position_before_start_to_dict(self):
        """未開始状態でも to_dict() が正常に動作"""
        bt = _create_bt()
        d = bt.position.to_dict()
        assert d == {"size": 0, "pl": 0, "pl_pct": 0, "is_long": False, "is_short": False}

    def test_position_before_start_close_noop(self):
        """未開始状態での close() はエラーなし"""
        bt = _create_bt()
        bt.position.close()  # should not raise


class TestPositionBool:
    """Position のブール値テスト"""

    def test_no_position_is_falsy(self):
        """ポジションなしはFalse"""
        bt = _create_bt()
        bt.goto(5)
        assert not bt.position

    def test_long_position_is_truthy(self):
        """ロングポジションはTrue"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        assert bt.position

    def test_short_position_is_truthy(self):
        """ショートポジションはTrue"""
        bt = _create_bt()
        bt.goto(5)
        bt.sell(code="TEST", size=10)
        bt.step()
        assert bt.position


class TestPositionSize:
    """Position.size のテスト"""

    def test_size_zero_when_no_trades(self):
        """取引なしの場合サイズ0"""
        bt = _create_bt()
        bt.goto(5)
        assert bt.position.size == 0

    def test_size_positive_for_long(self):
        """ロングポジションのサイズは正"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        assert bt.position.size > 0

    def test_size_negative_for_short(self):
        """ショートポジションのサイズは負"""
        bt = _create_bt()
        bt.goto(5)
        bt.sell(code="TEST", size=10)
        bt.step()
        assert bt.position.size < 0

    def test_size_is_sum_of_trades(self):
        """複数取引のサイズの合計"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        bt.buy(code="TEST", size=5)
        bt.step()
        assert bt.position.size == 15


class TestPositionPL:
    """Position.pl / pl_pct のテスト"""

    def test_pl_is_number(self):
        """P/Lが数値"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        bt.step()
        assert isinstance(bt.position.pl, (int, float))

    def test_pl_pct_is_number(self):
        """P/L%が数値"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        bt.step()
        assert isinstance(bt.position.pl_pct, (int, float))

    def test_pl_pct_zero_when_no_position(self):
        """ポジションなしの場合P/L%は0"""
        bt = _create_bt()
        bt.goto(5)
        assert bt.position.pl_pct == 0


class TestPositionDirection:
    """Position.is_long / is_short のテスト"""

    def test_is_long(self):
        """ロングポジション"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        assert bt.position.is_long is True
        assert bt.position.is_short is False

    def test_is_short(self):
        """ショートポジション"""
        bt = _create_bt()
        bt.goto(5)
        bt.sell(code="TEST", size=10)
        bt.step()
        assert bt.position.is_short is True
        assert bt.position.is_long is False

    def test_neither_when_flat(self):
        """ポジションなしの場合はどちらもFalse"""
        bt = _create_bt()
        bt.goto(5)
        assert bt.position.is_long is False
        assert bt.position.is_short is False


class TestPositionClose:
    """Position.close() のテスト"""

    def test_close_full(self):
        """全ポジション決済"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        assert bt.position.size > 0
        bt.position.close()
        bt.step()
        assert bt.position.size == 0

    def test_close_partial(self):
        """部分決済"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        initial_size = bt.position.size
        bt.position.close(portion=0.5)
        bt.step()
        assert bt.position.size < initial_size

    def test_close_short_position(self):
        """ショートポジションの決済"""
        bt = _create_bt()
        bt.goto(5)
        bt.sell(code="TEST", size=10)
        bt.step()
        assert bt.position.size < 0
        bt.position.close()
        bt.step()
        assert bt.position.size == 0
