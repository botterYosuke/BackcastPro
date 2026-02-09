"""
統計計算モジュール (_stats.py) のテスト
"""

import numpy as np
import pandas as pd
import pytest

from BackcastPro._stats import (
    compute_drawdown_duration_peaks,
    compute_stats,
    geometric_mean,
)


class TestGeometricMean:
    """geometric_mean() のテスト"""

    def test_positive_returns(self):
        """正のリターンの幾何平均"""
        returns = pd.Series([0.10, 0.05, 0.08])
        result = geometric_mean(returns)
        assert result > 0
        # (1.10 * 1.05 * 1.08)^(1/3) - 1 ≈ 0.0764
        assert abs(result - 0.0764) < 0.001

    def test_zero_returns(self):
        """全てゼロのリターン"""
        returns = pd.Series([0.0, 0.0, 0.0])
        result = geometric_mean(returns)
        assert result == 0.0

    def test_mixed_returns(self):
        """正負混在のリターン"""
        returns = pd.Series([0.10, -0.05, 0.03])
        result = geometric_mean(returns)
        assert isinstance(result, float)

    def test_return_below_negative_one(self):
        """リターンが-100%以下 → 0を返す"""
        returns = pd.Series([-1.5, 0.10])
        result = geometric_mean(returns)
        assert result == 0

    def test_empty_series(self):
        """空のSeries"""
        returns = pd.Series([], dtype=float)
        result = geometric_mean(returns)
        assert np.isnan(result)

    def test_single_return(self):
        """単一のリターン"""
        returns = pd.Series([0.05])
        result = geometric_mean(returns)
        assert abs(result - 0.05) < 1e-10

    def test_nan_filled_with_zero(self):
        """NaN値はゼロとして扱われる"""
        returns = pd.Series([0.10, np.nan, 0.05])
        result = geometric_mean(returns)
        # NaN → 0 → (1.10 * 1.0 * 1.05)^(1/3) - 1
        assert result > 0


class TestComputeDrawdownDurationPeaks:
    """compute_drawdown_duration_peaks() のテスト"""

    def test_no_drawdown(self):
        """ドローダウンなし（全てゼロ）"""
        dd = pd.Series(
            [0.0, 0.0, 0.0, 0.0, 0.0],
            index=pd.date_range("2024-01-01", periods=5),
        )
        duration, peaks = compute_drawdown_duration_peaks(dd)
        # ドローダウンがない場合、NaN系列が返る
        assert duration.isna().all()
        assert peaks.isna().all()

    def test_single_drawdown(self):
        """単一のドローダウン期間"""
        dd = pd.Series(
            [0.0, 0.05, 0.10, 0.03, 0.0],
            index=pd.date_range("2024-01-01", periods=5),
        )
        duration, peaks = compute_drawdown_duration_peaks(dd)
        # ピークドローダウンは0.10
        assert peaks.max() == pytest.approx(0.10)

    def test_multiple_drawdowns(self):
        """複数のドローダウン期間"""
        dd = pd.Series(
            [0.0, 0.05, 0.0, 0.10, 0.15, 0.0],
            index=pd.date_range("2024-01-01", periods=6),
        )
        duration, peaks = compute_drawdown_duration_peaks(dd)
        assert peaks.dropna().max() == pytest.approx(0.15)


class TestComputeStats:
    """compute_stats() のテスト"""

    def _make_trades_df(self):
        """テスト用のtrades DataFrameを生成"""
        return pd.DataFrame({
            "Code": ["TEST", "TEST"],
            "Size": [100, -100],
            "EntryBar": [0, 5],
            "ExitBar": [5, 10],
            "EntryPrice": [100.0, 110.0],
            "ExitPrice": [110.0, 105.0],
            "SL": [None, None],
            "TP": [None, None],
            "PnL": [1000.0, 500.0],
            "Commission": [10.0, 10.0],
            "ReturnPct": [0.10, 0.0455],
            "EntryTime": pd.to_datetime(["2024-01-01", "2024-01-06"]),
            "ExitTime": pd.to_datetime(["2024-01-06", "2024-01-11"]),
            "Duration": pd.to_timedelta(["5 days", "5 days"]),
            "Tag": [None, None],
        })

    def test_basic_stats(self):
        """基本的な統計値が正しく計算される"""
        index = pd.date_range("2024-01-01", periods=20)
        equity = np.linspace(10000, 11500, 20)
        trades_df = self._make_trades_df()

        stats = compute_stats(
            trades=trades_df,
            equity=equity,
            index=index,
            strategy_instance=None,
            risk_free_rate=0,
        )

        assert stats["Start"] == index[0]
        assert stats["End"] == index[-1]
        assert stats["# Trades"] == 2
        assert stats["Equity Final [$]"] == pytest.approx(11500.0)
        assert stats["Equity Peak [$]"] == pytest.approx(11500.0)
        assert stats["Return [%]"] == pytest.approx(15.0)
        assert stats["Win Rate [%]"] == pytest.approx(100.0)

    def test_stats_with_no_trades(self):
        """取引なしの場合"""
        index = pd.date_range("2024-01-01", periods=10)
        equity = np.full(10, 10000.0)
        trades_df = pd.DataFrame({
            "Code": pd.Series([], dtype=str),
            "Size": pd.Series([], dtype=float),
            "EntryBar": pd.Series([], dtype=int),
            "ExitBar": pd.Series([], dtype=int),
            "EntryPrice": pd.Series([], dtype=float),
            "ExitPrice": pd.Series([], dtype=float),
            "SL": pd.Series([], dtype=float),
            "TP": pd.Series([], dtype=float),
            "PnL": pd.Series([], dtype=float),
            "Commission": pd.Series([], dtype=float),
            "ReturnPct": pd.Series([], dtype=float),
            "EntryTime": pd.Series([], dtype="datetime64[ns]"),
            "ExitTime": pd.Series([], dtype="datetime64[ns]"),
            "Duration": pd.Series([], dtype="timedelta64[ns]"),
            "Tag": pd.Series([], dtype=object),
        })

        stats = compute_stats(
            trades=trades_df,
            equity=equity,
            index=index,
            strategy_instance=None,
            risk_free_rate=0,
        )

        assert stats["# Trades"] == 0
        assert stats["Return [%]"] == pytest.approx(0.0)
        assert np.isnan(stats["Win Rate [%]"])

    def test_stats_equity_length_mismatch(self):
        """equityとindexの長さが異なる場合"""
        index = pd.date_range("2024-01-01", periods=10)
        equity = np.linspace(10000, 11000, 15)  # indexより長い
        trades_df = self._make_trades_df()

        stats = compute_stats(
            trades=trades_df,
            equity=equity,
            index=index,
            strategy_instance=None,
            risk_free_rate=0,
        )
        # equityが切り詰められる
        assert stats["Equity Final [$]"] == pytest.approx(equity[9])

    def test_stats_contains_equity_curve(self):
        """_equity_curveが含まれる"""
        index = pd.date_range("2024-01-01", periods=20)
        equity = np.linspace(10000, 11000, 20)
        trades_df = self._make_trades_df()

        stats = compute_stats(
            trades=trades_df,
            equity=equity,
            index=index,
            strategy_instance=None,
        )

        assert isinstance(stats["_equity_curve"], pd.DataFrame)
        assert "Equity" in stats["_equity_curve"].columns
        assert "DrawdownPct" in stats["_equity_curve"].columns

    def test_stats_risk_free_rate_validation(self):
        """risk_free_rateの範囲チェック"""
        index = pd.date_range("2024-01-01", periods=10)
        equity = np.full(10, 10000.0)
        trades_df = self._make_trades_df()

        with pytest.raises(AssertionError):
            compute_stats(
                trades=trades_df,
                equity=equity,
                index=index,
                strategy_instance=None,
                risk_free_rate=1.5,
            )
