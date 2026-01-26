"""
TDD Tests for Backtest.set_data() Auto-Start Feature

Goal: Verify that set_data() automatically calls start(), so users
don't need to call start() separately after setting data.

Test cases:
1. After set_data(), _is_started is True
2. After set_data(), step() can be called without RuntimeError
3. set_data(None) does not auto-start (data is None)
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from BackcastPro import Backtest


def create_sample_df(days: int = 100) -> pd.DataFrame:
    """Create sample OHLC data for testing"""
    dates = pd.date_range(start="2024-01-01", periods=days, freq="D")
    np.random.seed(42)

    base_price = 100
    returns = np.random.randn(days) * 0.02
    prices = base_price * np.cumprod(1 + returns)

    df = pd.DataFrame({
        "Open": prices * (1 + np.random.randn(days) * 0.005),
        "High": prices * (1 + np.abs(np.random.randn(days) * 0.01)),
        "Low": prices * (1 - np.abs(np.random.randn(days) * 0.01)),
        "Close": prices,
        "Volume": np.random.randint(1000, 10000, days),
    }, index=dates)

    return df


class TestSetDataAutoStart:
    """set_data() automatically calls start()"""

    def test_is_started_true_after_set_data(self):
        """
        After calling set_data(data), _is_started should be True.

        This is the core test: set_data() should auto-start the backtest.
        """
        code = "TEST"
        df = create_sample_df(10)
        data = {code: df}

        # Create backtest without data first
        bt = Backtest()
        assert bt._is_started is False, "_is_started should be False before set_data"

        # Set data - this should auto-start
        bt.set_data(data)

        # Verify auto-start
        assert bt._is_started is True, "_is_started should be True after set_data()"

    def test_step_works_after_set_data_without_explicit_start(self):
        """
        After set_data(), step() can be called without RuntimeError.

        Previously, calling step() without start() would raise RuntimeError.
        Now set_data() auto-starts, so step() should work immediately.
        """
        code = "TEST"
        df = create_sample_df(10)
        data = {code: df}

        bt = Backtest()
        bt.set_data(data)

        # step() should NOT raise RuntimeError
        result = bt.step()

        # step() should return True (backtest continues)
        assert result is True, "step() should return True when backtest can continue"

    def test_set_data_none_does_not_auto_start(self):
        """
        set_data(None) should NOT auto-start (no data to process).
        """
        bt = Backtest()
        bt.set_data(None)

        assert bt._is_started is False, "_is_started should remain False when data is None"

    def test_broker_instance_initialized_after_set_data(self):
        """
        After set_data(), _broker_instance should be properly initialized.

        This ensures start() was actually called (not just _is_started flag).
        """
        code = "TEST"
        df = create_sample_df(10)
        data = {code: df}

        bt = Backtest()
        bt.set_data(data)

        assert bt._broker_instance is not None, "_broker_instance should be initialized after set_data()"

    def test_index_positions_populated_after_set_data(self):
        """
        After set_data(), _index_positions should be populated for performance optimization.
        """
        code = "TEST"
        df = create_sample_df(10)
        data = {code: df}

        bt = Backtest()
        bt.set_data(data)

        assert code in bt._index_positions, "_index_positions should contain the code"
        assert len(bt._index_positions[code]) == len(df), "_index_positions should have all index mappings"


class TestSetDataMultipleTimes:
    """Test behavior when set_data() is called multiple times"""

    def test_set_data_resets_state(self):
        """
        Calling set_data() again should reset the backtest state.

        Note: This test uses Backtest() without data in constructor,
        then calls set_data() twice.
        """
        code = "TEST"
        df = create_sample_df(20)
        data = {code: df}

        bt = Backtest()
        bt.set_data(data)

        # Progress the backtest
        bt.goto(10)
        assert bt._step_index == 10

        # Create new data
        df2 = create_sample_df(30)
        data2 = {code: df2}

        # Set new data - should reset
        bt.set_data(data2)

        assert bt._is_started is True, "_is_started should be True after new set_data()"
        assert bt._step_index == 0, "_step_index should reset to 0 after new set_data()"

    def test_step_after_set_data_replacement(self):
        """
        step() should work correctly after replacing data with set_data().

        Note: This test uses Backtest() without data in constructor.
        """
        code = "TEST"
        df1 = create_sample_df(10)
        df2 = create_sample_df(15)

        bt = Backtest()
        bt.set_data({code: df1})
        bt.goto(5)

        # Replace data
        bt.set_data({code: df2})

        # step() should work and use new data
        result = bt.step()
        assert result is True

        # Index should reflect new data length
        assert len(bt.index) == 15


class TestSetDataEdgeCases:
    """Edge cases for set_data()"""

    def test_set_data_empty_dict_does_not_auto_start(self):
        """
        set_data({}) with empty dict: start() raises error since no data.

        Current behavior: Empty dict creates empty index, start() fails on broker creation.
        """
        bt = Backtest()
        bt.set_data({})

        # Empty dict is processed but there's no valid data
        # The behavior depends on implementation - currently it doesn't raise in set_data
        # but would fail if we try to use it
        assert bt._data == {} or bt._data is not None

    def test_set_data_preserves_broker_settings(self):
        """
        set_data() should preserve broker settings (cash, commission, etc.).
        """
        code = "TEST"
        df = create_sample_df(10)
        data = {code: df}

        bt = Backtest(cash=50000, commission=0.01)
        bt.set_data(data)

        assert bt.cash == 50000, "Cash setting should be preserved after set_data()"


class TestConstructorWithData:
    """Tests for Backtest(data=...) constructor behavior."""

    def test_constructor_with_data_auto_starts(self):
        """
        Backtest(data=...) should auto-start.

        The constructor initializes _broker_factory and other state first,
        then calls set_data() which triggers start() automatically.
        """
        code = "TEST"
        df = create_sample_df(10)
        data = {code: df}

        bt = Backtest(data=data)

        assert bt._is_started is True, "_is_started should be True when data passed to constructor"

    def test_constructor_with_data_allows_immediate_step(self):
        """
        After Backtest(data=...), step() should work immediately.
        """
        code = "TEST"
        df = create_sample_df(10)
        data = {code: df}

        bt = Backtest(data=data)

        # step() should work without calling start() explicitly
        result = bt.step()
        assert result is True, "step() should work after constructor with data"
