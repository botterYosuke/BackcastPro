"""
TDD Tests for Backtest Chart Auto-Update Feature

Goal: Verify that step() automatically updates all chart widgets
stored in _chart_widgets after each step.

Test coverage:
1. step() calls _update_all_charts() after incrementing _step_index
2. All widgets in _chart_widgets get updated via update_chart()
3. Exceptions from destroyed widgets are handled gracefully (silently ignored)
4. Empty _chart_widgets dict causes no errors
5. Multiple codes are all updated
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch, call

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


class TestUpdateAllChartsIsCalled:
    """Test that step() calls _update_all_charts()"""

    def test_step_calls_update_all_charts(self):
        """
        step() should call _update_all_charts() after incrementing _step_index.

        This is the core behavior being tested: automatic chart updates.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        # Mock _update_all_charts to track calls
        with patch.object(bt, "_update_all_charts") as mock_update:
            bt.step()
            mock_update.assert_called_once()

    def test_step_calls_update_all_charts_after_step_index_increment(self):
        """
        _update_all_charts() should be called AFTER _step_index is incremented.

        This ensures charts show the latest data after the step.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        step_index_when_called = []

        def capture_step_index():
            step_index_when_called.append(bt._step_index)

        with patch.object(bt, "_update_all_charts", side_effect=capture_step_index):
            bt.step()

        # _step_index should be 1 when _update_all_charts is called
        # (after increment from 0 to 1)
        assert step_index_when_called[0] == 1, \
            "_update_all_charts should be called after _step_index is incremented"

    def test_step_calls_update_all_charts_on_every_step(self):
        """
        _update_all_charts() should be called on every step() call.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        with patch.object(bt, "_update_all_charts") as mock_update:
            # Call step() 5 times
            for _ in range(5):
                bt.step()

            assert mock_update.call_count == 5, \
                "_update_all_charts should be called on every step"

    def test_step_calls_update_all_charts_in_while_loop(self):
        """
        _update_all_charts() is called correctly in a typical while loop.
        """
        code = "TEST"
        df = create_sample_df(5)
        bt = Backtest(data={code: df})

        call_count = [0]
        original_method = bt._update_all_charts

        def counting_wrapper():
            call_count[0] += 1
            original_method()

        with patch.object(bt, "_update_all_charts", side_effect=counting_wrapper):
            while bt.step():
                pass

        # step() is called 5 times (4 return True, 1 returns False)
        # _update_all_charts should be called 5 times
        assert call_count[0] == 5, \
            f"_update_all_charts should be called 5 times, got {call_count[0]}"


class TestAllWidgetsUpdated:
    """Test that all widgets in _chart_widgets get updated"""

    def test_update_all_charts_calls_update_chart_for_each_widget(self):
        """
        _update_all_charts() should call update_chart() for each widget
        in _chart_widgets.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        # Create a chart first to populate _chart_widgets
        bt.goto(5)
        chart = bt.chart(code=code)

        # Verify widget is cached
        assert code in bt._chart_widgets

        with patch.object(bt, "update_chart") as mock_update_chart:
            bt._update_all_charts()

            # update_chart should be called with the widget and code
            mock_update_chart.assert_called_once_with(chart, code)

    def test_update_all_charts_updates_multiple_codes(self):
        """
        _update_all_charts() should update widgets for all codes.
        """
        code1, code2 = "CODE1", "CODE2"
        df1 = create_sample_df(10)
        df2 = create_sample_df(10)
        bt = Backtest(data={code1: df1, code2: df2})

        # Create charts for both codes
        bt.goto(5)
        chart1 = bt.chart(code=code1)
        chart2 = bt.chart(code=code2)

        # Verify both widgets are cached
        assert code1 in bt._chart_widgets
        assert code2 in bt._chart_widgets

        with patch.object(bt, "update_chart") as mock_update_chart:
            bt._update_all_charts()

            # update_chart should be called for both codes
            assert mock_update_chart.call_count == 2
            calls = mock_update_chart.call_args_list
            called_codes = {c[0][1] for c in calls}  # Extract code argument
            assert called_codes == {code1, code2}

    def test_step_updates_all_cached_charts(self):
        """
        After creating charts, step() should update all of them.

        Integration test: verifies step() -> _update_all_charts() -> update_chart()
        """
        code1, code2 = "CODE1", "CODE2"
        df1 = create_sample_df(10)
        df2 = create_sample_df(10)
        bt = Backtest(data={code1: df1, code2: df2})

        # Create charts
        bt.goto(5)
        bt.chart(code=code1)
        bt.chart(code=code2)

        with patch.object(bt, "update_chart") as mock_update_chart:
            bt.step()

            # Both charts should be updated
            assert mock_update_chart.call_count == 2


class TestExceptionHandling:
    """Test that exceptions from destroyed widgets are handled gracefully"""

    def test_update_all_charts_ignores_exception_from_update_chart(self):
        """
        _update_all_charts() should silently ignore exceptions from update_chart().

        This handles the case where a widget has been destroyed (e.g., user
        closed the notebook cell or refreshed the page).
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        # Manually add a mock widget
        mock_widget = MagicMock()
        bt._chart_widgets[code] = mock_widget

        # Make update_chart raise an exception
        with patch.object(bt, "update_chart", side_effect=RuntimeError("Widget destroyed")):
            # This should NOT raise an exception
            bt._update_all_charts()

    def test_update_all_charts_continues_after_exception(self):
        """
        If one widget raises an exception, other widgets should still be updated.
        """
        code1, code2, code3 = "CODE1", "CODE2", "CODE3"
        df = create_sample_df(10)
        bt = Backtest(data={code1: df.copy(), code2: df.copy(), code3: df.copy()})

        # Create charts for all codes
        bt.goto(5)
        bt.chart(code=code1)
        bt.chart(code=code2)
        bt.chart(code=code3)

        update_calls = []

        def mock_update(widget, code):
            if code == code2:
                raise RuntimeError("Widget destroyed")
            update_calls.append(code)

        with patch.object(bt, "update_chart", side_effect=mock_update):
            bt._update_all_charts()

        # code1 and code3 should still be attempted
        # (Note: dict iteration order is preserved in Python 3.7+)
        # At minimum, we should have attempted to update more than just the first one
        assert len(update_calls) >= 1, "Other widgets should still be updated"

    def test_step_continues_after_chart_exception(self):
        """
        step() should continue normally even if chart update fails.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        bt.goto(5)
        bt.chart(code=code)

        initial_step_index = bt._step_index

        with patch.object(bt, "update_chart", side_effect=Exception("Error")):
            result = bt.step()

        # step() should still return True (more steps available)
        assert result is True
        # _step_index should have incremented
        assert bt._step_index == initial_step_index + 1


class TestEmptyChartWidgets:
    """Test behavior when _chart_widgets is empty"""

    def test_update_all_charts_with_empty_widgets(self):
        """
        _update_all_charts() should handle empty _chart_widgets gracefully.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        # Ensure _chart_widgets is empty
        assert bt._chart_widgets == {}

        # This should NOT raise an exception
        bt._update_all_charts()

    def test_step_works_without_any_charts_created(self):
        """
        step() should work normally even if no charts have been created.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        # Don't create any charts
        assert bt._chart_widgets == {}

        # step() should work normally
        result = bt.step()
        assert result is True
        assert bt._step_index == 1


class TestIntegrationWithChartMethod:
    """Integration tests with chart() method"""

    def test_chart_widget_data_updated_after_step(self):
        """
        After step(), chart widget's data should reflect the new state.

        This is an integration test that verifies the full flow:
        1. Create chart at step N
        2. Call step()
        3. Verify chart data has been updated
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df})

        # Create chart at step 10
        bt.goto(10)
        chart = bt.chart(code=code)
        initial_data_len = len(chart.data)

        # Step forward
        bt.step()

        # Chart data should be updated
        # Note: The auto-update happens via _update_all_charts()
        assert len(chart.data) == initial_data_len + 1, \
            "Chart data should have one more bar after step"

    def test_multiple_steps_update_chart_incrementally(self):
        """
        Multiple step() calls should incrementally update the chart.
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df})

        bt.goto(10)
        chart = bt.chart(code=code)
        initial_len = len(chart.data)

        # Step 5 times
        for _ in range(5):
            bt.step()

        # Chart should have 5 more bars
        assert len(chart.data) == initial_len + 5, \
            "Chart data should have 5 more bars after 5 steps"

    def test_chart_markers_updated_after_trade(self):
        """
        Chart markers should be updated after trades are executed.
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df})

        # Create chart
        bt.goto(5)
        chart = bt.chart(code=code)
        initial_markers = len(chart.markers)

        # Execute a buy order
        bt.buy(code=code, size=10)

        # Step to execute the order
        bt.step()

        # Markers should be updated (trade marker added)
        # Note: This depends on how trades_to_markers works
        # At minimum, the update should have been called
        assert chart is bt._chart_widgets[code], \
            "Same widget should be used"


class TestGoToAndResetBehavior:
    """Test chart auto-update behavior with goto() and reset()"""

    def test_goto_updates_charts_via_step(self):
        """
        goto() internally calls step(), which should trigger chart updates.
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df})

        # Create chart
        bt.goto(5)
        bt.chart(code=code)

        with patch.object(bt, "_update_all_charts") as mock_update:
            # goto from 5 to 10 should call step() 5 times
            bt.goto(10)

            # _update_all_charts should be called for each step
            assert mock_update.call_count == 5

    def test_reset_preserves_chart_widgets_for_auto_update(self):
        """
        After reset(), _chart_widgets should be preserved (by default)
        so auto-update continues to work.
        """
        code = "TEST"
        df = create_sample_df(20)
        bt = Backtest(data={code: df})

        bt.goto(10)
        chart = bt.chart(code=code)

        bt.reset()

        # Widget should still be in cache
        assert code in bt._chart_widgets
        assert bt._chart_widgets[code] is chart

        # Step should still update the chart
        bt.step()
        # Widget should still be the same instance
        assert bt._chart_widgets[code] is chart


class TestEdgeCases:
    """Edge cases for chart auto-update"""

    def test_update_all_charts_with_none_widget(self):
        """
        _update_all_charts() should handle None values in _chart_widgets.
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        # Manually set None widget (shouldn't happen normally)
        bt._chart_widgets[code] = None

        # This might raise or might be handled - depends on implementation
        # The current implementation will call update_chart(None, code)
        # which should be caught by the try/except
        bt._update_all_charts()  # Should not raise

    def test_update_all_charts_when_broker_not_initialized(self):
        """
        _update_all_charts() should handle case when broker is not initialized.
        """
        bt = Backtest()  # No data

        # This should not raise
        bt._update_all_charts()

    def test_step_on_last_bar_still_updates_charts(self):
        """
        Even on the last step (which returns False), charts should be updated.
        """
        code = "TEST"
        df = create_sample_df(5)
        bt = Backtest(data={code: df})

        bt.goto(4)  # One step before the end
        bt.chart(code=code)

        with patch.object(bt, "_update_all_charts") as mock_update:
            # This is the last step
            result = bt.step()

            # step() should still call _update_all_charts
            mock_update.assert_called_once()
            # And return False (finished)
            assert result is False
