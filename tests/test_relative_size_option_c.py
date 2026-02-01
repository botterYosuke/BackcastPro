"""
TDD Tests for Relative Size Option C Fix

Goal: Verify that relative size (size omitted or -1 < size < 1) correctly
handles position closing behavior.

Problem:
When bt.sell() or bt.buy() is called without specifying size (relative size = 0.9999),
if there's an opposite position, it should close that position. But currently,
because margin_available is near zero after a buy, the calculated size becomes 0
and the order is cancelled before reaching the position close logic.

Solution (Option C):
- If opposite position exists: close all opposite positions
- If no opposite position: calculate based on equity (not margin_available)

Test Cases:
1. test_sell_closes_long_position - relative sell closes long position
2. test_buy_closes_short_position - relative buy closes short position
3. test_sell_full_short_when_no_position - no position, relative sell = full short
4. test_buy_full_long_when_no_position - no position, relative buy = full long
5. test_partial_relative_size_still_closes_all - size=0.5 with opposite position = full close
6. test_multi_symbol_isolation - different symbols don't affect each other
7. test_multi_symbol_fifo_isolation - FIFO close doesn't affect other symbols
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from BackcastPro import Backtest


def create_sample_df(days: int = 100, base_price: float = 1000.0) -> pd.DataFrame:
    """Create sample OHLC data for testing

    Args:
        days: Number of days of data
        base_price: Base price for the stock (default 1000 for easier calculation)
    """
    dates = pd.date_range(start="2024-01-01", periods=days, freq="D")
    np.random.seed(42)

    # Create stable prices for predictable testing
    returns = np.random.randn(days) * 0.01  # 1% volatility
    prices = base_price * np.cumprod(1 + returns)

    df = pd.DataFrame({
        "Open": prices * (1 + np.random.randn(days) * 0.002),
        "High": prices * (1 + np.abs(np.random.randn(days) * 0.005)),
        "Low": prices * (1 - np.abs(np.random.randn(days) * 0.005)),
        "Close": prices,
        "Volume": np.random.randint(1000, 10000, days),
    }, index=dates)

    return df


class TestRelativeSizeClosesOppositePosition:
    """Test that relative size orders close opposite positions"""

    def test_sell_closes_long_position(self):
        """
        Relative size sell should close all long positions.

        Scenario:
        1. Start with 1,000,000 cash
        2. Step to advance past step 0 (orders placed at step N execute at step N+1)
        3. Buy (size omitted) -> should create long position
        4. Step to execute buy
        5. Sell (size omitted) -> should close all long positions
        6. Step to execute sell
        7. Position should be 0
        """
        code = "7203"
        df = create_sample_df(20, base_price=1000.0)
        bt = Backtest(data={code: df}, cash=1_000_000)

        # Step to advance past initial state
        bt.step()

        # Buy with default relative size
        bt.buy(code=code)
        bt.step()  # Execute buy order

        initial_position = bt.position_of(code)
        assert initial_position > 0, f"Should have long position, got {initial_position}"

        # Sell with default relative size (should close long)
        bt.sell(code=code)
        bt.step()  # Execute sell order

        final_position = bt.position_of(code)
        assert final_position == 0, f"Position should be 0 (closed), got {final_position}"

    def test_buy_closes_short_position(self):
        """
        Relative size buy should close all short positions.

        Scenario:
        1. Start with 1,000,000 cash
        2. Step to advance past step 0
        3. Sell (size omitted) -> should create short position
        4. Step to execute sell
        5. Buy (size omitted) -> should close all short positions
        6. Step to execute buy
        7. Position should be 0
        """
        code = "7203"
        df = create_sample_df(20, base_price=1000.0)
        bt = Backtest(data={code: df}, cash=1_000_000)

        # Step to advance past initial state
        bt.step()

        # Sell with default relative size (short)
        bt.sell(code=code)
        bt.step()  # Execute sell order

        initial_position = bt.position_of(code)
        assert initial_position < 0, f"Should have short position, got {initial_position}"

        # Buy with default relative size (should close short)
        bt.buy(code=code)
        bt.step()  # Execute buy order

        final_position = bt.position_of(code)
        assert final_position == 0, f"Position should be 0 (closed), got {final_position}"


class TestRelativeSizeFullPositionWhenNoOpposite:
    """Test that relative size creates full position when no opposite exists"""

    def test_sell_full_short_when_no_position(self):
        """
        With no position, relative size sell should create full short position.

        Scenario:
        1. Start with 1,000,000 cash, no position
        2. Step to advance past step 0
        3. Sell (size omitted) -> should create short position using full equity
        4. Step to execute sell
        5. Should have negative (short) position
        """
        code = "7203"
        df = create_sample_df(20, base_price=1000.0)
        bt = Backtest(data={code: df}, cash=1_000_000)

        # Step to advance past initial state
        bt.step()

        assert bt.position_of(code) == 0, "Should start with no position"

        # Sell with default relative size
        bt.sell(code=code)
        bt.step()  # Execute sell order

        position = bt.position_of(code)
        assert position < 0, f"Should have short position, got {position}"

    def test_buy_full_long_when_no_position(self):
        """
        With no position, relative size buy should create full long position.

        Scenario:
        1. Start with 1,000,000 cash, no position
        2. Step to advance past step 0
        3. Buy (size omitted) -> should create long position using full equity
        4. Step to execute buy
        5. Should have positive (long) position
        """
        code = "7203"
        df = create_sample_df(20, base_price=1000.0)
        bt = Backtest(data={code: df}, cash=1_000_000)

        # Step to advance past initial state
        bt.step()

        assert bt.position_of(code) == 0, "Should start with no position"

        # Buy with default relative size
        bt.buy(code=code)
        bt.step()  # Execute buy order

        position = bt.position_of(code)
        assert position > 0, f"Should have long position, got {position}"


class TestPartialRelativeSizeClosesAll:
    """Test that partial relative sizes still close all opposite positions"""

    def test_partial_relative_size_still_closes_all(self):
        """
        Even with size=0.5, if there's an opposite position, it should close all.

        Design decision: When opposite position exists, any relative size
        should close ALL opposite positions.

        Scenario:
        1. Step to advance past step 0
        2. Buy to create long position
        3. Sell with size=0.5 (partial relative)
        4. Should still close ALL long positions (not 50%)
        """
        code = "7203"
        df = create_sample_df(20, base_price=1000.0)
        bt = Backtest(data={code: df}, cash=1_000_000)

        # Step to advance past initial state
        bt.step()

        # Buy with default relative size
        bt.buy(code=code)
        bt.step()  # Execute buy order

        initial_position = bt.position_of(code)
        assert initial_position > 0, f"Should have long position, got {initial_position}"

        # Sell with partial relative size (0.5)
        # Note: sell() internally converts to negative, so we pass 0.5
        bt.sell(code=code, size=0.5)
        bt.step()  # Execute sell order

        final_position = bt.position_of(code)
        assert final_position == 0, \
            f"Position should be 0 (all closed), got {final_position}"


class TestMultiSymbolIsolation:
    """Test that multi-symbol operations don't affect each other"""

    def test_multi_symbol_isolation(self):
        """
        Selling one symbol should not affect positions in other symbols.

        Scenario:
        1. Step to advance past step 0
        2. Buy both 7203 and 6758
        3. Sell only 7203
        4. 7203 position should be 0
        5. 6758 position should remain positive
        """
        code1 = "7203"
        code2 = "6758"
        df1 = create_sample_df(20, base_price=1000.0)

        # Use different random seed for second stock
        np.random.seed(123)
        df2 = create_sample_df(20, base_price=2000.0)

        bt = Backtest(data={code1: df1, code2: df2}, cash=1_000_000)

        # Step to advance past initial state
        bt.step()

        # Buy both symbols (use smaller sizes to have margin for both)
        bt.buy(code=code1, size=0.4)
        bt.buy(code=code2, size=0.4)
        bt.step()  # Execute buy orders

        pos1_before = bt.position_of(code1)
        pos2_before = bt.position_of(code2)
        assert pos1_before > 0, f"7203 should have long position, got {pos1_before}"
        assert pos2_before > 0, f"6758 should have long position, got {pos2_before}"

        # Sell only 7203
        bt.sell(code=code1)
        bt.step()  # Execute sell order

        pos1_after = bt.position_of(code1)
        pos2_after = bt.position_of(code2)

        assert pos1_after == 0, f"7203 should be closed (0), got {pos1_after}"
        assert pos2_after > 0, \
            f"6758 should be unchanged (positive), got {pos2_after}"

    def test_multi_symbol_fifo_isolation(self):
        """
        FIFO close processing should not affect other symbols.

        This tests the bug fix at L332 where trade.code check was missing.

        Scenario:
        1. Step to advance past step 0
        2. Buy 100 shares of 7203
        3. Buy 100 shares of 6758
        4. Sell 200 shares of 7203 (100 close + 100 new short)
        5. 7203 should be -100 (short)
        6. 6758 should still be 100 (unchanged)
        """
        code1 = "7203"
        code2 = "6758"
        df1 = create_sample_df(20, base_price=1000.0)

        np.random.seed(123)
        df2 = create_sample_df(20, base_price=2000.0)

        bt = Backtest(data={code1: df1, code2: df2}, cash=1_000_000)

        # Step to advance past initial state
        bt.step()

        # Buy specific sizes
        bt.buy(code=code1, size=100)
        bt.buy(code=code2, size=100)
        bt.step()  # Execute buy orders

        assert bt.position_of(code1) == 100, f"7203 should have 100, got {bt.position_of(code1)}"
        assert bt.position_of(code2) == 100, f"6758 should have 100, got {bt.position_of(code2)}"

        # Sell 200 shares of 7203 (100 close + 100 new short)
        bt.sell(code=code1, size=200)
        bt.step()  # Execute sell order

        pos1 = bt.position_of(code1)
        pos2 = bt.position_of(code2)

        assert pos1 == -100, f"7203 should be -100 (short), got {pos1}"
        assert pos2 == 100, f"6758 should still be 100 (unchanged), got {pos2}"


class TestEdgeCases:
    """Edge cases for relative size handling"""

    def test_multiple_buy_sell_cycles(self):
        """
        Multiple buy/sell cycles should work correctly.

        This simulates a typical trading scenario with alternating positions.
        """
        code = "7203"
        df = create_sample_df(50, base_price=1000.0)
        bt = Backtest(data={code: df}, cash=1_000_000)

        # Step to advance past initial state
        bt.step()

        # Cycle 1: Buy then Sell
        bt.buy(code=code)
        bt.step()
        assert bt.position_of(code) > 0, "Cycle 1: Should have long position"

        bt.sell(code=code)
        bt.step()
        assert bt.position_of(code) == 0, "Cycle 1: Position should be 0 after sell"

        # Cycle 2: Sell (short) then Buy
        bt.sell(code=code)
        bt.step()
        assert bt.position_of(code) < 0, "Cycle 2: Should have short position"

        bt.buy(code=code)
        bt.step()
        assert bt.position_of(code) == 0, "Cycle 2: Position should be 0 after buy"

        # Cycle 3: Buy again
        bt.buy(code=code)
        bt.step()
        assert bt.position_of(code) > 0, "Cycle 3: Should have long position again"

    def test_relative_size_with_absolute_size_mixed(self):
        """
        Absolute size orders should work correctly alongside relative size.

        Scenario:
        1. Step to advance past step 0
        2. Buy 50 shares (absolute)
        3. Sell (relative) -> should close all 50
        """
        code = "7203"
        df = create_sample_df(20, base_price=1000.0)
        bt = Backtest(data={code: df}, cash=1_000_000)

        # Step to advance past initial state
        bt.step()

        # Buy with absolute size
        bt.buy(code=code, size=50)
        bt.step()

        assert bt.position_of(code) == 50, f"Should have 50 shares, got {bt.position_of(code)}"

        # Sell with relative size (should close all 50)
        bt.sell(code=code)
        bt.step()

        assert bt.position_of(code) == 0, f"Position should be 0, got {bt.position_of(code)}"

    def test_equity_based_calculation_when_no_opposite_position(self):
        """
        When no opposite position exists, size should be calculated based on equity.

        This verifies the fix uses equity instead of margin_available.
        """
        code = "7203"
        df = create_sample_df(20, base_price=1000.0)
        bt = Backtest(data={code: df}, cash=1_000_000)

        # Step to advance past initial state
        bt.step()

        initial_equity = bt.equity
        assert initial_equity == 1_000_000, f"Initial equity should be 1M, got {initial_equity}"

        # Buy with relative size
        bt.buy(code=code)
        bt.step()

        # Position should be calculated based on equity (not margin_available which is 0 after buy)
        position = bt.position_of(code)
        assert position > 0, f"Should have created position based on equity, got {position}"

        # Rough check: with 1M cash and ~1000 price, should have ~999 shares (99.99%)
        # Allow for commission and spread adjustments
        assert position > 500, f"Position should be substantial, got {position}"


class TestWarningMessages:
    """Test that appropriate warnings are generated"""

    def test_no_warning_when_relative_size_closes_position(self):
        """
        When relative size successfully closes a position, no warning should be generated.

        Previously, the code would warn about "insufficient margin" even when
        the order should have closed an opposite position.
        """
        import warnings

        code = "7203"
        df = create_sample_df(20, base_price=1000.0)
        bt = Backtest(data={code: df}, cash=1_000_000)

        # Step to advance past initial state
        bt.step()

        # Buy first
        bt.buy(code=code)
        bt.step()
        assert bt.position_of(code) > 0

        # Sell should not generate warning
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            bt.sell(code=code)
            bt.step()

            # Filter for our specific warning
            margin_warnings = [
                warning for warning in w
                if "マージン" in str(warning.message) or "margin" in str(warning.message).lower()
            ]

            assert len(margin_warnings) == 0, \
                f"Should not have margin warning, got: {[str(w.message) for w in margin_warnings]}"

        # Position should be closed
        assert bt.position_of(code) == 0


class TestSameDirectionPositionAddition:
    """Test that relative size can add to same-direction positions using margin_available"""

    def test_buy_adds_to_long_position_with_margin_available(self):
        """
        Relative size buy should add to existing long position using margin_available.

        Scenario:
        1. Start with 1,000,000 cash
        2. Step to advance past step 0
        3. Buy with size=0.3 -> creates small long position (30% of equity)
        4. Step to execute buy
        5. Buy again (size omitted) -> should add to position using remaining margin
        6. Step to execute buy
        7. Position should increase (not be cancelled)
        """
        code = "7203"
        df = create_sample_df(20, base_price=1000.0)
        bt = Backtest(data={code: df}, cash=1_000_000)

        # Step to advance past initial state
        bt.step()

        # Buy with smaller size to leave margin available
        bt.buy(code=code, size=0.3)
        bt.step()  # Execute buy order

        initial_position = bt.position_of(code)
        assert initial_position > 0, f"Should have long position, got {initial_position}"

        # Buy again with relative size (should add to position)
        bt.buy(code=code)
        bt.step()  # Execute buy order

        final_position = bt.position_of(code)
        assert final_position > initial_position, \
            f"Position should increase: {initial_position} -> {final_position}"

    def test_sell_adds_to_short_position_with_margin_available(self):
        """
        Relative size sell should add to existing short position using margin_available.

        Scenario:
        1. Start with 1,000,000 cash
        2. Step to advance past step 0
        3. Sell with size=0.3 -> creates small short position (30% of equity)
        4. Step to execute sell
        5. Sell again (size omitted) -> should add to short using remaining margin
        6. Step to execute sell
        7. Position should become more negative (add to short)
        """
        code = "7203"
        df = create_sample_df(20, base_price=1000.0)
        bt = Backtest(data={code: df}, cash=1_000_000)

        # Step to advance past initial state
        bt.step()

        # Sell with smaller size to leave margin available
        bt.sell(code=code, size=0.3)
        bt.step()  # Execute sell order

        initial_position = bt.position_of(code)
        assert initial_position < 0, f"Should have short position, got {initial_position}"

        # Sell again with relative size (should add to short)
        bt.sell(code=code)
        bt.step()  # Execute sell order

        final_position = bt.position_of(code)
        assert final_position < initial_position, \
            f"Position should decrease (more negative): {initial_position} -> {final_position}"

    def test_no_margin_available_shows_warning(self):
        """
        When margin_available is 0 (full position), buy should show warning and cancel.

        Scenario:
        1. Start with 1,000,000 cash
        2. Step to advance past step 0
        3. Buy with size omitted -> creates full long position (uses all margin)
        4. Step to execute buy
        5. Buy again (size omitted) -> margin_available is 0
        6. Should show warning and cancel order
        7. Position should remain unchanged
        """
        import warnings

        code = "7203"
        df = create_sample_df(20, base_price=1000.0)
        bt = Backtest(data={code: df}, cash=1_000_000)

        # Step to advance past initial state
        bt.step()

        # Buy with full relative size (uses all margin)
        bt.buy(code=code)
        bt.step()  # Execute buy order

        initial_position = bt.position_of(code)
        assert initial_position > 0, f"Should have long position, got {initial_position}"

        # Buy again - margin_available should be ~0, so order should be cancelled
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            bt.buy(code=code)
            bt.step()

            # Filter for margin/資産 warning
            margin_warnings = [
                warning for warning in w
                if "不十分な資産" in str(warning.message) or "insufficient" in str(warning.message).lower()
            ]

            assert len(margin_warnings) > 0, \
                f"Should have margin warning, got: {[str(warning.message) for warning in w]}"

        # Position should remain unchanged
        final_position = bt.position_of(code)
        assert final_position == initial_position, \
            f"Position should remain unchanged: {initial_position} -> {final_position}"

    def test_partial_add_to_same_direction(self):
        """
        Relative size=0.5 should add 50% of margin_available to same direction.

        Scenario:
        1. Start with 1,000,000 cash
        2. Buy with size=0.3 (300 shares at 1000 yen)
        3. Buy again with size=0.5 -> should add ~50% of remaining margin
        """
        code = "7203"
        df = create_sample_df(20, base_price=1000.0)
        bt = Backtest(data={code: df}, cash=1_000_000)

        # Step to advance past initial state
        bt.step()

        # Buy with 30% of equity
        bt.buy(code=code, size=0.3)
        bt.step()

        first_position = bt.position_of(code)
        assert first_position > 0, f"Should have long position, got {first_position}"

        # Buy with 50% of remaining margin
        bt.buy(code=code, size=0.5)
        bt.step()

        final_position = bt.position_of(code)
        added_shares = final_position - first_position

        # Should have added some shares (not cancelled)
        assert added_shares > 0, \
            f"Should have added shares: first={first_position}, final={final_position}"

        # Added shares should be roughly 50% of remaining margin capacity
        # With 30% used, ~70% remaining, so adding 50% of 70% = ~35% of original capacity
        # This is a rough check - exact calculation depends on price and commission
        assert added_shares < first_position * 2, \
            f"Added shares should be less than double first position: added={added_shares}"
