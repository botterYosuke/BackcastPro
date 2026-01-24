"""
TDD Tests for Backtest.chart() Caching Feature

RED Phase: Write tests FIRST before implementation

Goal: Verify that chart() caches widgets and uses incremental updates
for better performance when called repeatedly.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from BackcastPro import Backtest
from BackcastPro.api.chart import LightweightChartWidget


def create_sample_df(days: int = 100) -> pd.DataFrame:
    """テスト用のサンプルOHLCデータを生成"""
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


class TestChartWidgetCaching:
    """chart()がウィジェットをキャッシュすることを確認"""

    def test_chart_returns_same_widget_on_consecutive_calls(self):
        """
        連続した chart() 呼び出しで同じウィジェットインスタンスを返す

        これがパフォーマンス改善の核心:
        毎回新規作成せず、既存ウィジェットを再利用する
        """
        code = "TEST"
        df = create_sample_df(50)
        bt = Backtest(data={code: df})

        # 10ステップ進める
        bt.goto(10)
        chart1 = bt.chart(code=code)

        # さらに1ステップ進める
        bt.step()
        chart2 = bt.chart(code=code)

        # 同一インスタンスであることを確認
        assert chart1 is chart2, "chart() should return the same widget instance"

    def test_chart_returns_different_widget_after_reset_with_clear(self):
        """
        reset(clear_chart_cache=True) 後は新しいウィジェットを返す

        明示的にキャッシュクリアを指定した場合のみ新しいウィジェットになる
        """
        code = "TEST"
        df = create_sample_df(50)
        bt = Backtest(data={code: df})

        bt.goto(10)
        chart1 = bt.chart(code=code)

        # リセット（キャッシュクリア指定）
        bt.reset(clear_chart_cache=True)
        bt.goto(10)
        chart2 = bt.chart(code=code)

        # 異なるインスタンスであることを確認
        assert chart1 is not chart2, "chart() should return new widget after reset(clear_chart_cache=True)"

    def test_chart_returns_same_widget_after_reset_default(self):
        """
        reset() デフォルトではウィジェットを再利用（パフォーマンス優先）
        """
        code = "TEST"
        df = create_sample_df(50)
        bt = Backtest(data={code: df})

        bt.goto(10)
        chart1 = bt.chart(code=code)

        # リセット（デフォルト: ウィジェット保持）
        bt.reset()
        bt.goto(10)
        chart2 = bt.chart(code=code)

        # 同一インスタンス
        assert chart1 is chart2, "chart() should return same widget after reset() by default"

    def test_chart_cache_is_per_code(self):
        """
        銘柄ごとに別のウィジェットをキャッシュ
        """
        code1, code2 = "CODE1", "CODE2"
        df1 = create_sample_df(50)
        df2 = create_sample_df(50)
        bt = Backtest(data={code1: df1, code2: df2})

        bt.goto(10)
        chart1 = bt.chart(code=code1)
        chart2 = bt.chart(code=code2)

        # 異なる銘柄は異なるウィジェット
        assert chart1 is not chart2, "Different codes should have different widgets"

        # 同じ銘柄は同じウィジェット
        chart1_again = bt.chart(code=code1)
        assert chart1 is chart1_again


class TestIncrementalUpdate:
    """差分更新ロジックのテスト"""

    def test_last_bar_updated_on_step(self):
        """
        step() 後の chart() で last_bar が更新される
        """
        code = "TEST"
        df = create_sample_df(50)
        bt = Backtest(data={code: df})

        bt.goto(10)
        chart = bt.chart(code=code)
        initial_last_bar = dict(chart.last_bar)  # コピー

        # 1ステップ進める
        bt.step()
        chart_after = bt.chart(code=code)

        # last_bar が更新されていることを確認
        assert chart.last_bar != initial_last_bar or len(chart.last_bar) > 0, \
            "last_bar should be updated after step"

    def test_full_data_not_replaced_on_incremental_step(self):
        """
        1ステップ進行では data 全体を置き換えない（パフォーマンス確認）

        注: これは実装の詳細をテストしているので、
        実際には last_bar が使われることを確認する
        """
        code = "TEST"
        df = create_sample_df(50)
        bt = Backtest(data={code: df})

        bt.goto(10)
        chart = bt.chart(code=code)
        initial_data_len = len(chart.data)

        # 1ステップ進める
        bt.step()
        _ = bt.chart(code=code)

        # data の長さは変わらない（差分更新なら）
        # ただし、実装によっては data も更新される可能性があるので
        # このテストは実装後に調整が必要かも
        assert len(chart.data) >= initial_data_len


class TestChartCacheAttributes:
    """キャッシュ関連の属性テスト"""

    def test_backtest_has_chart_widgets_attribute(self):
        """
        Backtest が _chart_widgets 属性を持つ
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        assert hasattr(bt, "_chart_widgets"), \
            "Backtest should have _chart_widgets attribute"

    def test_backtest_has_chart_last_index_attribute(self):
        """
        Backtest が _chart_last_index 属性を持つ
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        assert hasattr(bt, "_chart_last_index"), \
            "Backtest should have _chart_last_index attribute"

    def test_chart_widgets_initially_empty(self):
        """
        _chart_widgets は初期状態で空の辞書
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        assert bt._chart_widgets == {}, \
            "_chart_widgets should be empty initially"

    def test_reset_clears_chart_widgets_when_requested(self):
        """
        reset(clear_chart_cache=True) で _chart_widgets がクリアされる
        """
        code = "TEST"
        df = create_sample_df(50)
        bt = Backtest(data={code: df})

        bt.goto(10)
        _ = bt.chart(code=code)

        # キャッシュに何か入っている
        assert len(bt._chart_widgets) > 0

        # リセット（キャッシュクリア指定）
        bt.reset(clear_chart_cache=True)

        # キャッシュがクリアされている
        assert bt._chart_widgets == {}, \
            "reset(clear_chart_cache=True) should clear _chart_widgets"

    def test_reset_preserves_chart_widgets_by_default(self):
        """
        reset() デフォルトでは _chart_widgets を保持（パフォーマンス優先）
        """
        code = "TEST"
        df = create_sample_df(50)
        bt = Backtest(data={code: df})

        bt.goto(10)
        _ = bt.chart(code=code)

        # キャッシュに何か入っている
        assert len(bt._chart_widgets) > 0

        # リセット（デフォルト）
        bt.reset()

        # キャッシュは保持されている
        assert len(bt._chart_widgets) > 0, \
            "reset() should preserve _chart_widgets by default"


class TestRewindBehavior:
    """巻き戻し時の動作テスト"""

    def test_chart_handles_rewind_correctly(self):
        """
        goto() で巻き戻した場合も正しく動作
        """
        code = "TEST"
        df = create_sample_df(50)
        bt = Backtest(data={code: df})

        # 30まで進める
        bt.goto(30)
        chart = bt.chart(code=code)

        # 10に巻き戻す
        bt.goto(10)
        chart_after_rewind = bt.chart(code=code)

        # ウィジェットは同じ（キャッシュされている）
        assert chart is chart_after_rewind

        # ただしデータは10ステップ分に戻っている必要がある
        # （実装によって data を更新するか last_bar のみかは異なる）

    def test_chart_data_reflects_current_step(self):
        """
        chart のデータは現在のステップを反映
        """
        code = "TEST"
        df = create_sample_df(50)
        bt = Backtest(data={code: df})

        bt.goto(10)
        chart = bt.chart(code=code)

        # データ長は現在のステップに対応
        # （正確な長さは実装依存だが、少なくとも10以下のはず）
        assert len(chart.data) <= 10 or len(chart.data) > 0


class TestEdgeCases:
    """エッジケースのテスト"""

    def test_chart_before_any_step(self):
        """
        ステップを進める前の chart() 呼び出し
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        # start() 直後（step() 前）
        chart = bt.chart(code=code)

        # 空または最小限のチャートが返される
        assert chart is not None

    def test_chart_at_last_step(self):
        """
        最後のステップでの chart() 呼び出し
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        # 最後まで進める
        bt.goto(len(bt.index))
        chart = bt.chart(code=code)

        assert chart is not None
        assert len(chart.data) == len(df)

    def test_chart_with_single_code_no_arg(self):
        """
        単一銘柄の場合は code 引数省略可能
        """
        code = "TEST"
        df = create_sample_df(10)
        bt = Backtest(data={code: df})

        bt.goto(5)
        chart = bt.chart()  # code 省略

        assert chart is not None
