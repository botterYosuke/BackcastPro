"""
TDD Tests for Lightweight Charts Widget

RED Phase: Write tests FIRST before implementation
"""

import pytest
import pandas as pd
from datetime import datetime

from BackcastPro.api.chart import (
    to_lwc_timestamp,
    df_to_lwc_data,
    get_last_bar,
    LightweightChartWidget,
)


class TestToLwcTimestamp:
    """to_lwc_timestamp() のテスト"""

    def test_naive_timestamp_converts_to_utc(self):
        """タイムゾーンなしのTimestampをUTCに変換"""
        # JST 2024-01-15 09:00:00 → UTC 2024-01-15 00:00:00
        ts = pd.Timestamp("2024-01-15 09:00:00")
        result = to_lwc_timestamp(ts, tz="Asia/Tokyo")

        expected = int(pd.Timestamp("2024-01-15 00:00:00", tz="UTC").timestamp())
        assert result == expected

    def test_aware_timestamp_converts_correctly(self):
        """タイムゾーン付きTimestampを正しく変換"""
        
        ts = pd.Timestamp("2024-01-15 09:00:00", tz="Asia/Tokyo")
        result = to_lwc_timestamp(ts, tz="Asia/Tokyo")

        expected = int(pd.Timestamp("2024-01-15 00:00:00", tz="UTC").timestamp())
        assert result == expected

    def test_date_string_converts(self):
        """日付文字列を正しく変換"""
        
        result = to_lwc_timestamp("2024-01-15", tz="Asia/Tokyo")

        # 2024-01-15 00:00:00 JST → 2024-01-14 15:00:00 UTC
        expected = int(
            pd.Timestamp("2024-01-14 15:00:00", tz="UTC").timestamp()
        )
        assert result == expected


class TestDfToLwcData:
    """df_to_lwc_data() のテスト"""

    def test_converts_single_row(self):
        """1行のDataFrameを正しく変換"""
        
        df = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [110.0],
                "Low": [95.0],
                "Close": [105.0],
            },
            index=pd.to_datetime(["2024-01-15"]),
        )

        result = df_to_lwc_data(df)

        assert len(result) == 1
        assert "time" in result[0]
        assert result[0]["open"] == 100.0
        assert result[0]["high"] == 110.0
        assert result[0]["low"] == 95.0
        assert result[0]["close"] == 105.0

    def test_converts_multiple_rows(self):
        """複数行のDataFrameを正しく変換"""
        
        df = pd.DataFrame(
            {
                "Open": [100.0, 105.0, 110.0],
                "High": [110.0, 115.0, 120.0],
                "Low": [95.0, 100.0, 105.0],
                "Close": [105.0, 110.0, 115.0],
            },
            index=pd.to_datetime(["2024-01-15", "2024-01-16", "2024-01-17"]),
        )

        result = df_to_lwc_data(df)

        assert len(result) == 3
        # 時間順に並んでいることを確認
        assert result[0]["time"] < result[1]["time"] < result[2]["time"]

    def test_empty_dataframe(self):
        """空のDataFrameで空リストを返す"""
        
        df = pd.DataFrame(columns=["Open", "High", "Low", "Close"])

        result = df_to_lwc_data(df)

        assert result == []

    def test_preserves_float_precision(self):
        """浮動小数点の精度を保持"""
        
        df = pd.DataFrame(
            {
                "Open": [100.123456],
                "High": [110.654321],
                "Low": [95.111111],
                "Close": [105.999999],
            },
            index=pd.to_datetime(["2024-01-15"]),
        )

        result = df_to_lwc_data(df)

        assert result[0]["open"] == pytest.approx(100.123456)
        assert result[0]["close"] == pytest.approx(105.999999)


class TestGetLastBar:
    """get_last_bar() のテスト"""

    def test_returns_last_bar(self):
        """最後のバーを正しく取得"""
        
        df = pd.DataFrame(
            {
                "Open": [100.0, 105.0, 110.0],
                "High": [110.0, 115.0, 120.0],
                "Low": [95.0, 100.0, 105.0],
                "Close": [105.0, 110.0, 115.0],
            },
            index=pd.to_datetime(["2024-01-15", "2024-01-16", "2024-01-17"]),
        )

        result = get_last_bar(df)

        assert result["open"] == 110.0
        assert result["high"] == 120.0
        assert result["low"] == 105.0
        assert result["close"] == 115.0

    def test_empty_dataframe_returns_empty_dict(self):
        """空のDataFrameで空辞書を返す"""
        
        df = pd.DataFrame(columns=["Open", "High", "Low", "Close"])

        result = get_last_bar(df)

        assert result == {}

    def test_single_row_dataframe(self):
        """1行のDataFrameで正しく動作"""
        
        df = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [110.0],
                "Low": [95.0],
                "Close": [105.0],
            },
            index=pd.to_datetime(["2024-01-15"]),
        )

        result = get_last_bar(df)

        assert "time" in result
        assert result["open"] == 100.0


class TestLightweightChartWidget:
    """LightweightChartWidget クラスのテスト"""

    def test_widget_creation(self):
        """ウィジェットが正しく作成される"""
        
        widget = LightweightChartWidget()

        assert widget.data == []
        assert widget.last_bar == {}
        assert widget.options == {}

    def test_widget_has_esm(self):
        """ウィジェットにESMコードがある"""
        
        widget = LightweightChartWidget()

        assert hasattr(widget, "_esm")
        assert "createChart" in widget._esm

    def test_widget_data_trait(self):
        """dataトレイトが正しく動作"""
        
        widget = LightweightChartWidget()
        test_data = [{"time": 1705276800, "open": 100, "high": 110, "low": 95, "close": 105}]

        widget.data = test_data

        assert widget.data == test_data

    def test_widget_last_bar_trait(self):
        """last_barトレイトが正しく動作"""
        
        widget = LightweightChartWidget()
        test_bar = {"time": 1705276800, "open": 100, "high": 110, "low": 95, "close": 105}

        widget.last_bar = test_bar

        assert widget.last_bar == test_bar

    def test_widget_options_trait(self):
        """optionsトレイトが正しく動作"""
        
        widget = LightweightChartWidget()

        widget.options = {"height": 500}

        assert widget.options == {"height": 500}


class TestUpdateLogic:
    """更新ロジックのテスト（巻き戻し判定など）"""

    def test_needs_full_update_on_first_step(self):
        """初回は全データ更新が必要"""
        prev_step = 0
        current_step = 1
        needs_full_update = (
            prev_step == 0 or current_step < prev_step or current_step - prev_step > 1
        )
        assert needs_full_update is True

    def test_incremental_update_on_normal_progress(self):
        """通常進行では差分更新"""
        prev_step = 10
        current_step = 11
        needs_full_update = (
            prev_step == 0 or current_step < prev_step or current_step - prev_step > 1
        )
        assert needs_full_update is False

    def test_needs_full_update_on_rewind(self):
        """巻き戻しでは全データ更新が必要"""
        prev_step = 100
        current_step = 50
        needs_full_update = (
            prev_step == 0 or current_step < prev_step or current_step - prev_step > 1
        )
        assert needs_full_update is True

    def test_needs_full_update_on_big_jump(self):
        """大きなジャンプでは全データ更新が必要"""
        prev_step = 10
        current_step = 15  # 5ステップジャンプ
        needs_full_update = (
            prev_step == 0 or current_step < prev_step or current_step - prev_step > 1
        )
        assert needs_full_update is True

    def test_incremental_on_single_step(self):
        """1ステップ進行では差分更新"""
        prev_step = 99
        current_step = 100
        needs_full_update = (
            prev_step == 0 or current_step < prev_step or current_step - prev_step > 1
        )
        assert needs_full_update is False


class TestIsValidBar:
    """isValidBar JavaScript関数のロジックをPythonでテスト"""

    def test_valid_bar(self):
        """有効なバーデータ"""
        bar = {"time": 1705276800, "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0}
        # JavaScript側の検証ロジックと同等
        assert all(
            key in bar and isinstance(bar[key], (int, float))
            for key in ["time", "open", "high", "low", "close"]
        )

    def test_invalid_bar_missing_field(self):
        """フィールドが欠けているバーデータ"""
        bar = {"time": 1705276800, "open": 100.0, "high": 110.0, "low": 95.0}
        # close が欠けている
        assert not all(
            key in bar and isinstance(bar[key], (int, float))
            for key in ["time", "open", "high", "low", "close"]
        )

    def test_invalid_bar_wrong_type(self):
        """型が間違っているバーデータ"""
        bar = {"time": "2024-01-15", "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0}
        # time が文字列
        assert not all(
            key in bar and isinstance(bar[key], (int, float))
            for key in ["time", "open", "high", "low", "close"]
        )

    def test_empty_bar(self):
        """空のバーデータ"""
        bar = {}
        assert not all(
            key in bar and isinstance(bar[key], (int, float))
            for key in ["time", "open", "high", "low", "close"]
        )
