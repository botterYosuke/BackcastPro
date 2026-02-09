"""
取引管理モジュール (trade.py) のテスト
"""

import numpy as np
import pandas as pd
import pytest
import warnings

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


class TestTradeProperties:
    """Trade のプロパティテスト"""

    def _open_long_trade(self):
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        assert len(bt.trades) == 1
        return bt, bt.trades[0]

    def _open_short_trade(self):
        bt = _create_bt()
        bt.goto(5)
        bt.sell(code="TEST", size=10)
        bt.step()
        assert len(bt.trades) == 1
        return bt, bt.trades[0]

    def test_trade_code(self):
        """Trade.code が正しい"""
        _, trade = self._open_long_trade()
        assert trade.code == "TEST"

    def test_trade_size_long(self):
        """ロングTradeのサイズが正"""
        _, trade = self._open_long_trade()
        assert trade.size > 0

    def test_trade_size_short(self):
        """ショートTradeのサイズが負"""
        _, trade = self._open_short_trade()
        assert trade.size < 0

    def test_trade_entry_price(self):
        """エントリー価格が正の値"""
        _, trade = self._open_long_trade()
        assert trade.entry_price > 0

    def test_trade_exit_price_none_when_active(self):
        """アクティブなTradeのexit_priceはNone"""
        _, trade = self._open_long_trade()
        assert trade.exit_price is None

    def test_trade_entry_time(self):
        """エントリー時間がTimestamp"""
        _, trade = self._open_long_trade()
        assert isinstance(trade.entry_time, pd.Timestamp)

    def test_trade_exit_time_none_when_active(self):
        """アクティブなTradeのexit_timeはNone"""
        _, trade = self._open_long_trade()
        assert trade.exit_time is None

    def test_trade_is_long(self):
        """ロング判定"""
        _, trade = self._open_long_trade()
        assert trade.is_long is True
        assert trade.is_short is False

    def test_trade_is_short(self):
        """ショート判定"""
        _, trade = self._open_short_trade()
        assert trade.is_short is True
        assert trade.is_long is False

    def test_trade_pl_is_number(self):
        """P/Lが数値"""
        bt, trade = self._open_long_trade()
        bt.step()
        assert isinstance(trade.pl, (int, float))

    def test_trade_pl_pct_is_number(self):
        """P/L%が数値"""
        bt, trade = self._open_long_trade()
        bt.step()
        assert isinstance(trade.pl_pct, (int, float))

    def test_trade_value_is_positive(self):
        """Trade.valueは常に正"""
        _, trade = self._open_long_trade()
        assert trade.value > 0

    def test_trade_tag(self):
        """Trade.tagが伝播される"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10, tag="my_tag")
        bt.step()
        trade = bt.trades[0]
        assert trade.tag == "my_tag"


class TestTradeClose:
    """Trade.close() のテスト"""

    def test_close_creates_order(self):
        """close()で決済注文が生成される"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        trade = bt.trades[0]
        trade.close()
        assert len(bt.orders) == 1

    def test_close_full_position(self):
        """全ポジション決済"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        trade = bt.trades[0]
        trade.close()
        bt.step()
        assert len(bt.trades) == 0
        assert len(bt.closed_trades) == 1

    def test_close_partial(self):
        """部分決済"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        trade = bt.trades[0]
        trade.close(portion=0.5)
        bt.step()
        # 部分的にクローズされた
        assert len(bt.closed_trades) >= 1

    def test_close_invalid_portion(self):
        """不正なportionでAssertionError"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        trade = bt.trades[0]
        with pytest.raises(AssertionError):
            trade.close(portion=0)
        with pytest.raises(AssertionError):
            trade.close(portion=1.5)


class TestClosedTradeProperties:
    """決済済みTradeのプロパティテスト"""

    def test_closed_trade_has_exit_price(self):
        """決済済みTradeにexit_priceがある"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        bt.trades[0].close()
        bt.step()
        closed = bt.closed_trades[0]
        assert closed.exit_price is not None
        assert closed.exit_price > 0

    def test_closed_trade_has_exit_time(self):
        """決済済みTradeにexit_timeがある"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        bt.trades[0].close()
        bt.step()
        closed = bt.closed_trades[0]
        assert closed.exit_time is not None
        assert isinstance(closed.exit_time, pd.Timestamp)

    def test_closed_trade_pl_includes_commission(self):
        """決済済みTradeのP/Lに手数料が含まれる"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        bt.trades[0].close()
        bt.step()
        closed = bt.closed_trades[0]
        assert closed._commissions >= 0


class TestTradeDeprecatedProperties:
    """非推奨プロパティのテスト"""

    def test_entry_bar_deprecated(self):
        """entry_barは非推奨警告を出す"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        trade = bt.trades[0]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _ = trade.entry_bar
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)

    def test_exit_bar_deprecated(self):
        """exit_barは非推奨警告を出す"""
        bt = _create_bt()
        bt.goto(5)
        bt.buy(code="TEST", size=10)
        bt.step()
        trade = bt.trades[0]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _ = trade.exit_bar
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
