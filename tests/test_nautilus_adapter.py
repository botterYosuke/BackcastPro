# -*- coding: utf-8 -*-
"""
NautilusBacktest ユニットテスト

nautilus_adapter.py (NautilusBacktest) が BackcastPro.Backtest と
同じ API を提供することを検証する。
"""
import sys
import os

import pandas as pd
import numpy as np
import pytest

# nautilus_adapter.py が marimo/src-tauri/resources/files/ にあるためパスを追加
# BackcastPro/tests/ → BackcastPro/ → Documents/ → marimo/src-tauri/resources/files/
_FILES_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "marimo", "src-tauri", "resources", "files"
)
sys.path.insert(0, os.path.abspath(_FILES_DIR))

from nautilus_adapter import NautilusBacktest, BankruptError


# ---------------------------------------------------------------------------
# テスト用合成データ生成
# ---------------------------------------------------------------------------

def create_synthetic_df(days: int = 30, start_price: float = 2500.0) -> pd.DataFrame:
    """テスト用 OHLCV DataFrame を生成する"""
    dates = pd.date_range(start="2024-01-01", periods=days, freq="B")  # 営業日
    np.random.seed(42)
    prices = start_price + np.cumsum(np.random.randn(days) * 10)
    prices = np.maximum(prices, 100)  # 負値防止

    df = pd.DataFrame(
        {
            "Open": prices * (1 + np.random.randn(days) * 0.002),
            "High": prices * (1 + np.abs(np.random.randn(days) * 0.005)),
            "Low": prices * (1 - np.abs(np.random.randn(days) * 0.005)),
            "Close": prices,
            "Volume": np.random.randint(1000, 10000, days).astype(float),
        },
        index=dates,
    )
    return df


SYNTHETIC_DF = create_synthetic_df(30)


# ---------------------------------------------------------------------------
# Phase 0 互換確認
# ---------------------------------------------------------------------------

class TestPhase0Compat:
    """BackcastPro 互換 API の存在確認"""

    def test_trades_is_property_not_callable(self):
        """`bt.trades` が property であり callable でないこと"""
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        assert not callable(bt.trades), "bt.trades は property であり関数ではない"

    def test_has_chart_state_compatible_interface(self):
        """_chart_state は NautilusBacktest 側で透過的に設定できること（動的属性）"""
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        bt._chart_state = object()  # 動的属性として設定できる
        assert hasattr(bt, "_chart_state")


# ---------------------------------------------------------------------------
# Phase 1: ステップ実行
# ---------------------------------------------------------------------------

class TestStepExecution:
    """step() の基本動作"""

    def test_step_increments_step_index(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        assert bt.step_index == 0
        bt.step()
        assert bt.step_index == 1
        bt.step()
        assert bt.step_index == 2

    def test_step_returns_true_while_running(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        result = bt.step()
        assert result is True

    def test_step_returns_false_when_finished(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        while bt.step():
            pass
        assert bt.step() is False
        assert bt.is_finished is True

    def test_is_finished_false_at_start(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        assert bt.is_finished is False


# ---------------------------------------------------------------------------
# データ可視性
# ---------------------------------------------------------------------------

class TestDataVisibility:
    """戦略呼び出し時の current_data 可視性"""

    def test_current_data_visible_to_strategy(self):
        """step() 内で戦略が呼ばれる時点で現在バーが bt.data に見えること"""
        seen_lengths = []

        def strategy(bt):
            if "7203" in bt.data:
                seen_lengths.append(len(bt.data["7203"]))

        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        bt.set_strategy(strategy)
        bt.step()  # step 1
        bt.step()  # step 2

        assert seen_lengths == [1, 2], (
            f"戦略実行時のデータ行数が想定と異なる: {seen_lengths}"
        )

    def test_set_data_auto_starts(self):
        """set_data() 後に明示的 start() なしで step() が動作すること"""
        bt = NautilusBacktest(cash=100_000)
        bt.set_data({"7203": SYNTHETIC_DF})
        assert bt.step() is True

    def test_constructor_with_data_auto_starts(self):
        """コンストラクタで data を渡した場合も step() が動作すること"""
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        assert bt.step() is True


# ---------------------------------------------------------------------------
# 買い注文と equity
# ---------------------------------------------------------------------------

class TestBuyAndEquity:
    """買い注文と資産計算"""

    def test_equity_equals_initial_cash_before_step(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        assert bt.equity == pytest.approx(100_000, rel=0.01)

    def test_buy_reduces_cash(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=1_000_000)
        bt.step()
        initial_cash = bt.cash
        bt.buy(code="7203", size=100)
        bt.step()  # 注文約定
        assert bt.cash < initial_cash

    def test_buy_creates_open_position(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=1_000_000)
        bt.step()
        bt.buy(code="7203", size=100)
        bt.step()  # 注文約定
        assert bt.position_of("7203") == 100

    def test_trades_contains_open_position(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=1_000_000)
        bt.step()
        bt.buy(code="7203", size=100)
        bt.step()
        assert len(bt.trades) >= 1
        assert bt.trades[0].code == "7203"
        assert bt.trades[0].size == 100

    def test_equity_reflects_mtm(self):
        """equity が現金 + 保有株の時価を反映すること"""
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=1_000_000)
        bt.step()
        bt.buy(code="7203", size=100)
        bt.step()
        # equity = cash + position * current_close
        cash = bt.cash
        pos_size = bt.position_of("7203")
        close = float(bt.data["7203"]["Close"].iloc[-1])
        expected_equity = cash + pos_size * close
        assert bt.equity == pytest.approx(expected_equity, rel=0.01)


# ---------------------------------------------------------------------------
# 売り注文
# ---------------------------------------------------------------------------

class TestSell:
    """売り注文"""

    def test_sell_closes_position(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=1_000_000)
        bt.step()
        bt.buy(code="7203", size=100)
        bt.step()  # 買い約定
        assert bt.position_of("7203") == 100
        bt.sell(code="7203", size=100)
        bt.step()  # 売り約定
        assert bt.position_of("7203") == 0

    def test_sell_all_via_trade_close(self):
        """trade.close() でポジションをクローズできること"""
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=1_000_000)
        bt.step()
        bt.buy(code="7203", size=100)
        bt.step()
        for trade in bt.trades:
            if trade.code == "7203":
                trade.close()
        bt.step()
        assert bt.position_of("7203") == 0


# ---------------------------------------------------------------------------
# goto
# ---------------------------------------------------------------------------

class TestGoto:
    """goto() のステップジャンプ"""

    def test_goto_forward(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        bt.goto(5)
        assert bt.step_index == 5

    def test_goto_backward_resets(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        bt.goto(10)
        bt.goto(3)
        assert bt.step_index == 3

    def test_goto_zero_equivalent_to_reset(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        bt.goto(10)
        bt.goto(0)
        assert bt.step_index == 0


# ---------------------------------------------------------------------------
# プロパティ
# ---------------------------------------------------------------------------

class TestProperties:
    """各プロパティの動作"""

    def test_current_time_is_none_before_step(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        assert bt.current_time is None

    def test_current_time_updates_after_step(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        bt.step()
        assert bt.current_time is not None

    def test_progress_is_zero_at_start(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        assert bt.progress == 0.0

    def test_progress_increases_with_steps(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        bt.goto(5)
        assert bt.progress > 0.0

    def test_step_index_is_read_only(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        with pytest.raises(AttributeError):
            bt.step_index = 5

    def test_data_attribute_accessible(self):
        """_data 属性にアクセスできること（reveal_data() 互換）"""
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        assert "7203" in bt._data
        assert isinstance(bt._data["7203"], pd.DataFrame)


# ---------------------------------------------------------------------------
# finalize
# ---------------------------------------------------------------------------

class TestFinalize:
    """finalize() の動作"""

    def test_finalize_returns_series(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        while not bt.is_finished:
            bt.step()
        result = bt.finalize()
        assert isinstance(result, pd.Series)

    def test_finalize_has_required_keys(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        bt.run()
        result = bt.finalize()
        for key in ("Equity Final [$]", "Return [%]", "# Trades"):
            assert key in result, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# get_state_snapshot
# ---------------------------------------------------------------------------

class TestGetStateSnapshot:
    """get_state_snapshot() の動作"""

    def test_returns_dict(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        result = bt.get_state_snapshot()
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        result = bt.get_state_snapshot()
        for key in (
            "current_time", "progress", "equity", "cash",
            "position", "positions", "closed_trades", "step_index", "total_steps"
        ):
            assert key in result, f"Missing key: {key}"

    def test_step_index_matches(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        bt.goto(5)
        snapshot = bt.get_state_snapshot()
        assert snapshot["step_index"] == bt.step_index == 5

    def test_current_time_dash_before_step(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        snapshot = bt.get_state_snapshot()
        assert snapshot["current_time"] == "-"


# ---------------------------------------------------------------------------
# add_trade_callback
# ---------------------------------------------------------------------------

class TestTradeCallback:
    """add_trade_callback() の動作"""

    def test_callback_called_on_buy(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=1_000_000)
        events = []
        bt.add_trade_callback(lambda evt, trade: events.append((evt, trade.code)))
        bt.step()
        bt.buy(code="7203", size=100)
        bt.step()
        assert len(events) > 0

    def test_callback_receives_buy_event(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=1_000_000)
        event_types = []
        bt.add_trade_callback(lambda evt, trade: event_types.append(evt))
        bt.step()
        bt.buy(code="7203", size=100)
        bt.step()
        assert "BUY" in event_types

    def test_multiple_callbacks(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=1_000_000)
        calls1, calls2 = [], []
        bt.add_trade_callback(lambda e, t: calls1.append(e))
        bt.add_trade_callback(lambda e, t: calls2.append(e))
        bt.step()
        bt.buy(code="7203", size=100)
        bt.step()
        assert len(calls1) > 0
        assert len(calls2) > 0


# ---------------------------------------------------------------------------
# reset / set_cash
# ---------------------------------------------------------------------------

class TestResetAndSetCash:
    """reset() と set_cash() の動作"""

    def test_reset_resets_step_index(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        bt.goto(10)
        bt.reset()
        assert bt.step_index == 0

    def test_reset_clears_positions(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=1_000_000)
        bt.step()
        bt.buy(code="7203", size=100)
        bt.step()
        bt.reset()
        assert bt.position_of("7203") == 0

    def test_set_cash_takes_effect_after_reset(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=100_000)
        bt.set_cash(500_000)
        bt.reset()
        assert bt.equity == pytest.approx(500_000, rel=0.01)


# ---------------------------------------------------------------------------
# 全 API メソッドの smoke test
# ---------------------------------------------------------------------------

class TestAllApiMethods:
    """全メソッド・プロパティが例外なく呼び出せること"""

    def test_all_api_smoke(self):
        bt = NautilusBacktest(data={"7203": SYNTHETIC_DF}, cash=500_000)
        bt.set_cash(500_000)
        bt.set_strategy(lambda b: None)
        bt.start()
        bt.step()
        _ = bt.equity
        _ = bt.cash
        _ = bt.trades
        _ = bt.closed_trades
        _ = bt.orders
        _ = bt.position
        _ = bt.position_of("7203")
        _ = bt.data
        _ = bt.current_time
        _ = bt.progress
        _ = bt.step_index
        _ = bt.is_finished
        _ = bt.get_state_snapshot()
        bt.add_trade_callback(lambda e, t: None)
        bt.reset()
        bt.goto(3)
        result = bt.run()
        assert isinstance(result, pd.Series)
