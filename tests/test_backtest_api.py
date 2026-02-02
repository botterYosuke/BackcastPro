"""
TDD Tests for BackcastPro Public API Extensions

Goal: Add public API for marimo-independent state access and callback mechanism.

Phase 1 Tests:
1. step_index property - read-only access to _step_index
2. get_state_snapshot() - returns current state as dict (marimo-independent)
3. add_trade_callback() - multiple callback registration for trade events

These tests follow TDD (Red-Green-Refactor):
- First write failing tests (RED)
- Then implement minimal code to pass (GREEN)
- Then refactor for quality (REFACTOR)
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


# =============================================================================
# Test: step_index property
# =============================================================================

class TestStepIndexProperty:
    """Test that step_index property provides read-only access to _step_index"""

    def test_step_index_returns_zero_at_start(self):
        """
        step_index property should return 0 after initialization.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        assert bt.step_index == 0, "step_index should be 0 at start"

    def test_step_index_returns_current_step(self):
        """
        step_index property should reflect current step position.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        bt.step()
        bt.step()
        bt.step()

        assert bt.step_index == 3, "step_index should be 3 after 3 steps"

    def test_step_index_equals_internal_step_index(self):
        """
        step_index property should always equal _step_index.
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df})

        bt.goto(15)

        assert bt.step_index == bt._step_index, \
            "step_index should equal _step_index"

    def test_step_index_is_read_only(self):
        """
        step_index property should be read-only (no setter).
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        with pytest.raises(AttributeError):
            bt.step_index = 5  # Should raise AttributeError


# =============================================================================
# Test: get_state_snapshot()
# =============================================================================

class TestGetStateSnapshot:
    """Test get_state_snapshot() returns complete state dictionary"""

    def test_get_state_snapshot_returns_dict(self):
        """
        get_state_snapshot() should return a dictionary.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        result = bt.get_state_snapshot()

        assert isinstance(result, dict), "get_state_snapshot should return a dict"

    def test_get_state_snapshot_contains_required_keys(self):
        """
        get_state_snapshot() should contain all required keys.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        result = bt.get_state_snapshot()

        required_keys = [
            "current_time",
            "progress",
            "equity",
            "cash",
            "position",
            "positions",
            "closed_trades",
            "step_index",
            "total_steps",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_get_state_snapshot_step_index_matches(self):
        """
        get_state_snapshot()['step_index'] should match bt.step_index.
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df})

        bt.goto(10)
        result = bt.get_state_snapshot()

        assert result["step_index"] == bt.step_index, \
            "step_index in snapshot should match bt.step_index"
        assert result["step_index"] == 10

    def test_get_state_snapshot_total_steps_matches_index_length(self):
        """
        get_state_snapshot()['total_steps'] should match len(bt.index).
        """
        code = "TEST"
        df = create_sample_df(50)
        bt = Backtest(data={code: df})

        result = bt.get_state_snapshot()

        assert result["total_steps"] == len(bt.index), \
            "total_steps should match len(bt.index)"
        assert result["total_steps"] == 50

    def test_get_state_snapshot_progress_is_float(self):
        """
        get_state_snapshot()['progress'] should be a float between 0 and 1.
        """
        code = "TEST"
        df = create_sample_df(100)
        bt = Backtest(data={code: df})

        bt.goto(50)
        result = bt.get_state_snapshot()

        assert isinstance(result["progress"], float), \
            "progress should be a float"
        assert 0.0 <= result["progress"] <= 1.0, \
            "progress should be between 0 and 1"
        assert abs(result["progress"] - 0.5) < 0.01, \
            "progress should be approximately 0.5 at step 50 of 100"

    def test_get_state_snapshot_equity_and_cash_are_floats(self):
        """
        get_state_snapshot() equity and cash should be floats.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df}, cash=50000)

        result = bt.get_state_snapshot()

        assert isinstance(result["equity"], float), "equity should be float"
        assert isinstance(result["cash"], float), "cash should be float"
        assert result["cash"] == 50000.0, "initial cash should be 50000"

    def test_get_state_snapshot_positions_dict(self):
        """
        get_state_snapshot()['positions'] should be a dict of code -> size.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        result = bt.get_state_snapshot()

        assert isinstance(result["positions"], dict), \
            "positions should be a dict"

    def test_get_state_snapshot_positions_after_buy(self):
        """
        get_state_snapshot()['positions'] should reflect open positions.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df}, cash=100000)

        # Execute some steps and buy
        bt.step()
        bt.buy(code=code, size=10)
        bt.step()  # Order executes

        result = bt.get_state_snapshot()

        # Should have position in TEST
        assert code in result["positions"] or result["position"] > 0, \
            "Should have position after buy"

    def test_get_state_snapshot_closed_trades_count(self):
        """
        get_state_snapshot()['closed_trades'] should be count of closed trades.
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df}, cash=100000)

        # Execute buy and sell
        bt.step()
        bt.buy(code=code, size=10)
        bt.step()
        bt.step()
        bt.sell(code=code, size=10)
        bt.step()
        bt.step()

        result = bt.get_state_snapshot()

        assert isinstance(result["closed_trades"], int), \
            "closed_trades should be an integer"

    def test_get_state_snapshot_current_time_string(self):
        """
        get_state_snapshot()['current_time'] should be a string.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        bt.step()
        result = bt.get_state_snapshot()

        assert isinstance(result["current_time"], str), \
            "current_time should be a string"
        assert result["current_time"] != "-", \
            "current_time should not be '-' after step"

    def test_get_state_snapshot_current_time_before_step(self):
        """
        get_state_snapshot()['current_time'] should be '-' before any step.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        result = bt.get_state_snapshot()

        assert result["current_time"] == "-", \
            "current_time should be '-' before any step"

    def test_get_state_snapshot_is_pure_function(self):
        """
        get_state_snapshot() should not modify backtest state.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        bt.goto(5)
        step_before = bt.step_index
        equity_before = bt.equity

        # Call get_state_snapshot multiple times
        bt.get_state_snapshot()
        bt.get_state_snapshot()
        bt.get_state_snapshot()

        assert bt.step_index == step_before, \
            "get_state_snapshot should not modify step_index"
        assert bt.equity == equity_before, \
            "get_state_snapshot should not modify equity"


# =============================================================================
# Test: add_trade_callback()
# =============================================================================

class TestAddTradeCallback:
    """Test add_trade_callback() for multiple callback registration"""

    def test_add_trade_callback_accepts_callable(self):
        """
        add_trade_callback() should accept a callable.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        def my_callback(event_type: str, trade):
            pass

        # Should not raise
        bt.add_trade_callback(my_callback)

    def test_add_trade_callback_is_called_on_trade(self):
        """
        Registered callback should be called when a trade occurs.
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df}, cash=100000)

        callback_calls = []

        def my_callback(event_type: str, trade):
            callback_calls.append({
                "event_type": event_type,
                "code": trade.code,
                "size": trade.size,
            })

        bt.add_trade_callback(my_callback)

        # Execute buy
        bt.step()
        bt.buy(code=code, size=10)
        bt.step()  # Order should execute

        assert len(callback_calls) > 0, \
            "Callback should be called when trade occurs"

    def test_add_trade_callback_multiple_callbacks(self):
        """
        Multiple callbacks can be registered and all are called.
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df}, cash=100000)

        callback1_calls = []
        callback2_calls = []
        callback3_calls = []

        def callback1(event_type: str, trade):
            callback1_calls.append(event_type)

        def callback2(event_type: str, trade):
            callback2_calls.append(event_type)

        def callback3(event_type: str, trade):
            callback3_calls.append(event_type)

        bt.add_trade_callback(callback1)
        bt.add_trade_callback(callback2)
        bt.add_trade_callback(callback3)

        # Execute buy
        bt.step()
        bt.buy(code=code, size=10)
        bt.step()

        # All callbacks should be called
        assert len(callback1_calls) > 0, "callback1 should be called"
        assert len(callback2_calls) > 0, "callback2 should be called"
        assert len(callback3_calls) > 0, "callback3 should be called"

    def test_add_trade_callback_preserves_order(self):
        """
        Callbacks should be called in the order they were registered.
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df}, cash=100000)

        call_order = []

        def callback1(event_type: str, trade):
            call_order.append(1)

        def callback2(event_type: str, trade):
            call_order.append(2)

        def callback3(event_type: str, trade):
            call_order.append(3)

        bt.add_trade_callback(callback1)
        bt.add_trade_callback(callback2)
        bt.add_trade_callback(callback3)

        # Execute buy
        bt.step()
        bt.buy(code=code, size=10)
        bt.step()

        # Order should be 1, 2, 3
        assert call_order == [1, 2, 3], \
            f"Callbacks should be called in order, got {call_order}"

    def test_add_trade_callback_receives_event_type(self):
        """
        Callback should receive event_type ('BUY' or 'SELL').
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df}, cash=100000)

        event_types = []

        def my_callback(event_type: str, trade):
            event_types.append(event_type)

        bt.add_trade_callback(my_callback)

        # Execute buy
        bt.step()
        bt.buy(code=code, size=10)
        bt.step()

        assert len(event_types) > 0, "Should receive event_type"
        assert event_types[0] in ("BUY", "SELL"), \
            f"event_type should be 'BUY' or 'SELL', got {event_types[0]}"

    def test_add_trade_callback_receives_trade_object(self):
        """
        Callback should receive trade object with code, size, entry_price.
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df}, cash=100000)

        trade_objects = []

        def my_callback(event_type: str, trade):
            trade_objects.append(trade)

        bt.add_trade_callback(my_callback)

        # Execute buy
        bt.step()
        bt.buy(code=code, size=10)
        bt.step()

        assert len(trade_objects) > 0, "Should receive trade object"
        trade = trade_objects[0]
        assert hasattr(trade, "code"), "Trade should have code attribute"
        assert hasattr(trade, "size"), "Trade should have size attribute"
        assert hasattr(trade, "entry_price"), "Trade should have entry_price attribute"

    def test_add_trade_callback_before_start(self):
        """
        Callbacks registered before start() should work after start().
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df}, cash=100000)

        callback_calls = []

        def my_callback(event_type: str, trade):
            callback_calls.append(event_type)

        # Register callback (data already set, so start() was called)
        bt.add_trade_callback(my_callback)

        # Reset and run again
        bt.reset()

        # Execute buy
        bt.step()
        bt.buy(code=code, size=10)
        bt.step()

        assert len(callback_calls) > 0, \
            "Callback should work after reset"

    def test_add_trade_callback_with_trade_event_publisher(self):
        """
        add_trade_callback should work alongside existing _trade_event_publisher.

        This tests backward compatibility with the existing mechanism.
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df}, cash=100000)

        # Simulate _trade_event_publisher being set (legacy mechanism)
        class MockPublisher:
            def __init__(self):
                self.calls = []

            def emit_from_trade(self, trade, is_opening=True):
                self.calls.append(trade)

        publisher = MockPublisher()
        bt._trade_event_publisher = publisher

        # Add new callback
        new_callback_calls = []

        def new_callback(event_type: str, trade):
            new_callback_calls.append(event_type)

        bt.add_trade_callback(new_callback)

        # Reset to apply callbacks
        bt.reset()

        # Execute buy
        bt.step()
        bt.buy(code=code, size=10)
        bt.step()

        # Both should work (publisher may or may not be called depending on implementation)
        # At minimum, new callback should work
        assert len(new_callback_calls) > 0, \
            "New callback should work alongside _trade_event_publisher"


# =============================================================================
# Test: _trade_callbacks attribute
# =============================================================================

class TestTradeCallbacksAttribute:
    """Test that _trade_callbacks list is properly initialized"""

    def test_trade_callbacks_initialized_as_list(self):
        """
        _trade_callbacks should be initialized as an empty list.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        assert hasattr(bt, "_trade_callbacks"), \
            "Backtest should have _trade_callbacks attribute"
        assert isinstance(bt._trade_callbacks, list), \
            "_trade_callbacks should be a list"

    def test_trade_callbacks_empty_initially(self):
        """
        _trade_callbacks should be empty initially.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        assert len(bt._trade_callbacks) == 0, \
            "_trade_callbacks should be empty initially"

    def test_trade_callbacks_grows_with_add(self):
        """
        _trade_callbacks should grow when add_trade_callback is called.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        def cb1(e, t):
            pass

        def cb2(e, t):
            pass

        bt.add_trade_callback(cb1)
        assert len(bt._trade_callbacks) == 1

        bt.add_trade_callback(cb2)
        assert len(bt._trade_callbacks) == 2


# =============================================================================
# Integration Test: Combined usage
# =============================================================================

class TestIntegration:
    """Integration tests for combined API usage"""

    def test_state_snapshot_with_callbacks(self):
        """
        get_state_snapshot() should work correctly with trade callbacks.
        """
        code = "TEST"
        df = create_sample_df(30)
        bt = Backtest(data={code: df}, cash=100000)

        trade_count = [0]

        def on_trade(event_type: str, trade):
            trade_count[0] += 1

        bt.add_trade_callback(on_trade)

        # Execute some trades
        bt.step()
        bt.buy(code=code, size=10)
        bt.step()
        bt.step()

        # Get state snapshot
        snapshot = bt.get_state_snapshot()

        assert snapshot["step_index"] == bt.step_index
        assert snapshot["step_index"] == 3
        assert isinstance(snapshot["positions"], dict)

    def test_step_index_in_callback(self):
        """
        bt.step_index should be accessible and correct inside callback.
        """
        code = "TEST"
        df = create_sample_df(30)
        bt = Backtest(data={code: df}, cash=100000)

        step_indices_in_callback = []

        def on_trade(event_type: str, trade):
            step_indices_in_callback.append(bt.step_index)

        bt.add_trade_callback(on_trade)

        # Execute trades at different steps
        bt.goto(5)
        bt.buy(code=code, size=10)
        bt.step()

        bt.goto(15)
        bt.buy(code=code, size=5)
        bt.step()

        # step_index should be captured correctly
        assert len(step_indices_in_callback) >= 1, \
            "Should have recorded step_index in callbacks"
