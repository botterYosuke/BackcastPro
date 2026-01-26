"""
TDD Tests for Backtest Step Loop Mechanism

Goal: Verify that the step loop mechanism works correctly for game loop integration.
This tests the core backtest step behavior that the marimo game loop relies on:

1. bt.step() increments _step_index correctly
2. bt.step() returns True while there are more steps
3. bt.step() returns False when finished
4. bt.is_finished reflects the correct state
5. Multiple step() calls in a loop work correctly

These tests do NOT test marimo UI parts (mo.state, mo.Thread),
but focus on the underlying BackcastPro logic.
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


class TestStepIndexIncrement:
    """Test that step() increments _step_index correctly"""

    def test_step_index_starts_at_zero(self):
        """
        _step_index should be 0 after initialization.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        assert bt._step_index == 0, "_step_index should start at 0"

    def test_step_increments_step_index_by_one(self):
        """
        Each step() call should increment _step_index by 1.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        initial_index = bt._step_index
        bt.step()

        assert bt._step_index == initial_index + 1, \
            "step() should increment _step_index by 1"

    def test_multiple_steps_increment_correctly(self):
        """
        Multiple step() calls should increment _step_index correctly.
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df})

        # Call step() 5 times
        for _ in range(5):
            bt.step()

        assert bt._step_index == 5, \
            "After 5 steps, _step_index should be 5"

    def test_step_index_after_goto(self):
        """
        After goto(n), _step_index should be n.
        """
        code = "TEST"
        df = create_sample_df(50)
        bt = Backtest(data={code: df})

        bt.goto(25)

        assert bt._step_index == 25, \
            "After goto(25), _step_index should be 25"


class TestStepReturnValue:
    """Test that step() returns the correct boolean value"""

    def test_step_returns_true_when_more_steps_available(self):
        """
        step() should return True when backtest can continue.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        result = bt.step()

        assert result is True, \
            "step() should return True when more steps are available"

    def test_step_returns_true_until_last_step(self):
        """
        step() should return True for all steps except the last one.
        """
        code = "TEST"
        df = create_sample_df(5)
        bt = Backtest(data={code: df})

        results = []
        for _ in range(5):
            results.append(bt.step())

        # First 4 steps should return True, last should return False
        assert results[:4] == [True, True, True, True], \
            "step() should return True for steps before the last"
        assert results[4] is False, \
            "step() should return False on the last step"

    def test_step_returns_false_when_finished(self):
        """
        step() should return False when backtest is finished.
        """
        code = "TEST"
        df = create_sample_df(3)
        bt = Backtest(data={code: df})

        # Exhaust all steps
        while bt.step():
            pass

        # Next step should also return False
        result = bt.step()

        assert result is False, \
            "step() should return False when backtest is finished"

    def test_step_returns_false_after_is_finished_true(self):
        """
        Once is_finished is True, step() should always return False.
        """
        code = "TEST"
        df = create_sample_df(3)
        bt = Backtest(data={code: df})

        # Run until finished
        bt.run()

        # Verify is_finished is True
        assert bt.is_finished is True

        # step() should return False
        assert bt.step() is False, \
            "step() should return False when is_finished is True"


class TestIsFinishedProperty:
    """Test that is_finished reflects the correct state"""

    def test_is_finished_false_at_start(self):
        """
        is_finished should be False after initialization.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        assert bt.is_finished is False, \
            "is_finished should be False at start"

    def test_is_finished_false_during_backtest(self):
        """
        is_finished should remain False while steps are available.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        bt.step()
        bt.step()
        bt.step()

        assert bt.is_finished is False, \
            "is_finished should be False during backtest"

    def test_is_finished_true_after_all_steps(self):
        """
        is_finished should be True after all steps are consumed.
        """
        code = "TEST"
        df = create_sample_df(5)
        bt = Backtest(data={code: df})

        # Consume all steps
        while bt.step():
            pass

        assert bt.is_finished is True, \
            "is_finished should be True after all steps consumed"

    def test_is_finished_true_after_run(self):
        """
        is_finished should be True after run() completes.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        bt.run()

        assert bt.is_finished is True, \
            "is_finished should be True after run()"

    def test_is_finished_false_after_reset(self):
        """
        is_finished should be False after reset().
        """
        code = "TEST"
        df = create_sample_df(5)
        bt = Backtest(data={code: df})

        # Finish the backtest
        bt.run()
        assert bt.is_finished is True

        # Reset
        bt.reset()

        assert bt.is_finished is False, \
            "is_finished should be False after reset()"


class TestStepLoop:
    """Test step() behavior in a loop (simulating game loop)"""

    def test_step_loop_processes_all_data(self):
        """
        A while loop calling step() should process all data points.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        step_count = 0
        while bt.step():
            step_count += 1

        # Should have processed exactly len(df) steps
        # (last step returns False, so step_count is len(df) - 1 + 1 final False)
        # Actually, step returns False ON the last step, so we get len(df) - 1 True returns
        assert step_count == len(df) - 1, \
            f"Loop should process {len(df) - 1} steps (got {step_count})"

    def test_step_loop_with_callback(self):
        """
        Step loop with a callback function (simulating chart update).
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        step_indices = []

        while bt.step():
            step_indices.append(bt._step_index)

        # Should capture indices 1 through len(df)-1
        expected = list(range(1, len(df)))
        assert step_indices == expected, \
            f"Step indices should be {expected}, got {step_indices}"

    def test_step_loop_respects_early_termination(self):
        """
        Step loop can be terminated early (simulating pause/stop).
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df})

        step_count = 0
        while bt.step():
            step_count += 1
            if step_count >= 5:
                break  # Early termination

        assert step_count == 5, "Loop should stop after 5 steps"
        assert bt.is_finished is False, \
            "is_finished should be False after early termination"

    def test_step_loop_can_resume_after_break(self):
        """
        Step loop can resume after early termination.
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df})

        # First loop: 5 steps
        step_count = 0
        while bt.step():
            step_count += 1
            if step_count >= 5:
                break

        first_index = bt._step_index

        # Resume: 5 more steps
        additional_steps = 0
        while bt.step():
            additional_steps += 1
            if additional_steps >= 5:
                break

        assert bt._step_index == first_index + 5, \
            "Step index should continue from where it left off"


class TestGameLoopSimulation:
    """
    Simulate the marimo game loop pattern:

    def _game_loop():
        while bt.is_finished == False:
            if not get_playing():
                break
            if bt.step() == False:
                break
            set_step(bt._step_index)
            time.sleep(0.5)
    """

    def test_game_loop_pattern_basic(self):
        """
        Test the basic game loop pattern without marimo state.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df}, finalize_trades=True)

        playing = True
        step_updates = []

        while bt.is_finished == False:
            if not playing:
                break
            if bt.step() == False:
                break
            step_updates.append(bt._step_index)

        # Should have recorded all step indices
        assert len(step_updates) == len(df) - 1, \
            f"Should have {len(df) - 1} step updates"

    def test_game_loop_pattern_with_pause(self):
        """
        Test game loop with pause (playing = False).
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df}, finalize_trades=True)

        playing = True
        step_updates = []

        while bt.is_finished == False:
            if not playing:
                break
            if bt.step() == False:
                break
            step_updates.append(bt._step_index)
            if len(step_updates) >= 5:
                playing = False  # Pause

        assert len(step_updates) == 5, "Should pause after 5 steps"
        assert bt.is_finished is False, "Should not be finished after pause"

    def test_game_loop_pattern_with_resume(self):
        """
        Test game loop resume after pause.
        """
        code = "TEST"
        df = create_sample_df(15)
        bt = Backtest(data={code: df}, finalize_trades=True)

        playing = True
        all_step_updates = []

        # First run: 5 steps
        while bt.is_finished == False:
            if not playing:
                break
            if bt.step() == False:
                break
            all_step_updates.append(bt._step_index)
            if len(all_step_updates) >= 5:
                playing = False

        # Resume
        playing = True
        while bt.is_finished == False:
            if not playing:
                break
            if bt.step() == False:
                break
            all_step_updates.append(bt._step_index)

        # Should have all steps now
        assert len(all_step_updates) == len(df) - 1, \
            f"Should have {len(df) - 1} total step updates"


class TestStepIndexConsistency:
    """Test _step_index consistency across operations"""

    def test_step_index_equals_progress_times_total(self):
        """
        _step_index should be consistent with progress property.
        """
        code = "TEST"
        df = create_sample_df(100)
        bt = Backtest(data={code: df})

        bt.goto(50)

        expected_progress = 50 / len(df)
        assert abs(bt.progress - expected_progress) < 0.001, \
            f"progress should be {expected_progress}, got {bt.progress}"

    def test_step_index_consistent_after_multiple_operations(self):
        """
        _step_index should be consistent after goto/step/reset operations.
        """
        code = "TEST"
        df = create_sample_df(50)
        bt = Backtest(data={code: df})

        # Various operations
        bt.goto(25)
        bt.step()
        bt.step()

        assert bt._step_index == 27, "_step_index should be 27"

        # Goto back
        bt.goto(10)

        assert bt._step_index == 10, "_step_index should be 10 after goto"


class TestStepWithStrategy:
    """Test step() with strategy function"""

    def test_step_calls_strategy(self):
        """
        step() should call the strategy function if set.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        call_count = [0]

        def strategy(backtest):
            call_count[0] += 1

        bt.set_strategy(strategy)

        # Call step() 5 times
        for _ in range(5):
            bt.step()

        assert call_count[0] == 5, \
            f"Strategy should be called 5 times, got {call_count[0]}"

    def test_step_in_loop_calls_strategy_each_time(self):
        """
        Strategy should be called on every step() in a loop.

        Note: Strategy is called at the beginning of step(), BEFORE
        checking if we've reached the end. So for a 10-bar dataset:
        - step() is called 10 times (indices 0-9)
        - strategy is called 10 times (before index increment)
        - step() returns True 9 times, False 1 time (on the last call)
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        strategy_step_indices = []

        def strategy(backtest):
            strategy_step_indices.append(backtest._step_index)

        bt.set_strategy(strategy)

        while bt.step():
            pass

        # Strategy is called on every step() invocation, including the final
        # one that returns False. So indices should be 0 through len(df)-1.
        # The while loop calls step() len(df) times total (9 True + 1 False).
        expected = list(range(len(df)))
        assert strategy_step_indices == expected, \
            f"Strategy indices should be {expected}, got {strategy_step_indices}"


class TestEdgeCases:
    """Edge cases for step loop"""

    def test_step_with_single_bar_data(self):
        """
        step() with only 1 bar of data.
        """
        code = "TEST"
        df = create_sample_df(1)
        bt = Backtest(data={code: df})

        result = bt.step()

        # With only 1 bar, step should process it and return False (finished)
        assert result is False, \
            "step() with 1 bar should return False immediately"
        assert bt.is_finished is True, \
            "is_finished should be True after processing single bar"

    def test_step_with_two_bars_data(self):
        """
        step() with 2 bars of data.
        """
        code = "TEST"
        df = create_sample_df(2)
        bt = Backtest(data={code: df})

        # First step
        result1 = bt.step()
        assert result1 is True, "First step should return True"
        assert bt._step_index == 1

        # Second step
        result2 = bt.step()
        assert result2 is False, "Second step should return False (finished)"
        assert bt.is_finished is True

    def test_step_after_run_does_nothing(self):
        """
        step() after run() should return False and not change state.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        bt.run()
        final_index = bt._step_index

        result = bt.step()

        assert result is False
        assert bt._step_index == final_index, \
            "_step_index should not change after run()"

    def test_step_without_data_raises_error(self):
        """
        step() without data should raise an error.
        """
        bt = Backtest()

        with pytest.raises(RuntimeError, match="start"):
            bt.step()


class TestMultipleStocksStepLoop:
    """Test step loop with multiple stocks"""

    def test_step_loop_with_multiple_stocks(self):
        """
        Step loop works correctly with multiple stocks.
        """
        code1 = "STOCK1"
        code2 = "STOCK2"
        df1 = create_sample_df(10)
        df2 = create_sample_df(10)
        bt = Backtest(data={code1: df1, code2: df2})

        step_count = 0
        while bt.step():
            step_count += 1

        # Index is unified, so should process all dates
        assert step_count == len(bt.index) - 1

    def test_step_loop_with_different_length_stocks(self):
        """
        Step loop with stocks of different lengths.
        """
        code1 = "STOCK1"
        code2 = "STOCK2"
        df1 = create_sample_df(10)
        df2 = create_sample_df(15)  # Longer
        bt = Backtest(data={code1: df1, code2: df2})

        step_count = 0
        while bt.step():
            step_count += 1

        # Index should contain all unique dates
        # The exact count depends on date overlap
        assert step_count == len(bt.index) - 1


class TestStrategyDataAccess:
    """
    Test that strategy can access bt.data during step().

    This is critical for the marimo game loop where the strategy
    needs to read current data on each step.
    """

    def test_strategy_can_access_data_on_first_step(self):
        """
        Strategy should be able to access bt.data[code] on the very first step().

        BUG DETECTED: Previously, strategy was called BEFORE _current_data was
        populated, causing KeyError when strategy tried to access bt.data[code].

        This test ensures strategy is called AFTER data is available.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        data_accessed = [False]
        error_occurred = [None]

        def strategy(backtest):
            try:
                # This should NOT raise KeyError
                current_data = backtest.data[code]
                data_accessed[0] = True
                assert len(current_data) > 0, "Data should not be empty"
            except KeyError as e:
                error_occurred[0] = e

        bt.set_strategy(strategy)

        # First step should not raise KeyError
        bt.step()

        assert error_occurred[0] is None, \
            f"Strategy should be able to access bt.data[code], got KeyError: {error_occurred[0]}"
        assert data_accessed[0] is True, \
            "Strategy should have successfully accessed data"

    def test_strategy_data_grows_with_steps(self):
        """
        bt.data[code] should contain progressively more data as steps progress.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        data_lengths = []

        def strategy(backtest):
            data_lengths.append(len(backtest.data[code]))

        bt.set_strategy(strategy)

        # Run through all steps
        while bt.step():
            pass

        # Data length should increase with each step
        # First step should have 1 row, second should have 2, etc.
        expected = list(range(1, len(df) + 1))
        assert data_lengths == expected, \
            f"Data lengths should be {expected}, got {data_lengths}"

    def test_strategy_accesses_correct_slice(self):
        """
        bt.data[code] should return data up to current step, not full data.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        def strategy(backtest):
            current_data = backtest.data[code]
            # Should only see data up to current step
            assert current_data.index[-1] == bt.index[bt._step_index], \
                "Last data point should match current step index"

        bt.set_strategy(strategy)

        # Run 5 steps
        for _ in range(5):
            bt.step()
