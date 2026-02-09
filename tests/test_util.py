"""
ユーティリティモジュール (util.py) のテスト
"""

from datetime import date, datetime

import pandas as pd
import pytest

from trading_data.lib.util import PRICE_LIMIT_TABLE, _Timestamp


class TestTimestamp:
    """_Timestamp() のテスト"""

    def test_none_returns_none(self):
        """Noneを渡すとNoneが返る"""
        assert _Timestamp(None) is None

    def test_string_date(self):
        """文字列日付をTimestampに変換"""
        result = _Timestamp("2024-01-15")
        assert isinstance(result, pd.Timestamp)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_datetime_object(self):
        """datetimeオブジェクトをTimestampに変換"""
        dt = datetime(2024, 6, 15, 10, 30)
        result = _Timestamp(dt)
        assert isinstance(result, pd.Timestamp)
        assert result.year == 2024
        assert result.month == 6

    def test_date_object(self):
        """dateオブジェクトをTimestampに変換"""
        d = date(2024, 3, 1)
        result = _Timestamp(d)
        assert isinstance(result, pd.Timestamp)
        assert result.year == 2024
        assert result.month == 3

    def test_pd_timestamp(self):
        """pd.Timestampはそのまま返される"""
        ts = pd.Timestamp("2024-01-01")
        result = _Timestamp(ts)
        assert result == ts

    def test_invalid_string_raises(self):
        """不正な文字列でValueError"""
        with pytest.raises(ValueError, match="日付パラメータの形式が不正"):
            _Timestamp("not-a-date")

    def test_japanese_date_format(self):
        """日本語日付形式"""
        result = _Timestamp("2024/01/15")
        assert isinstance(result, pd.Timestamp)
        assert result.day == 15

    def test_iso_format(self):
        """ISO 8601形式"""
        result = _Timestamp("2024-01-15T10:30:00")
        assert isinstance(result, pd.Timestamp)
        assert result.hour == 10
        assert result.minute == 30


class TestPriceLimitTable:
    """PRICE_LIMIT_TABLE のテスト"""

    def test_table_is_list(self):
        """テーブルがリスト"""
        assert isinstance(PRICE_LIMIT_TABLE, list)

    def test_table_not_empty(self):
        """テーブルが空でない"""
        assert len(PRICE_LIMIT_TABLE) > 0

    def test_table_entries_are_tuples(self):
        """各エントリがタプル"""
        for entry in PRICE_LIMIT_TABLE:
            assert isinstance(entry, tuple)
            assert len(entry) == 2

    def test_table_sorted_by_price(self):
        """価格上限が昇順"""
        prices = [entry[0] for entry in PRICE_LIMIT_TABLE]
        assert prices == sorted(prices)

    def test_table_last_entry_is_inf(self):
        """最後のエントリの上限がinf"""
        assert PRICE_LIMIT_TABLE[-1][0] == float("inf")

    def test_table_widths_are_positive(self):
        """値幅が全て正"""
        for _, width in PRICE_LIMIT_TABLE:
            assert width > 0

    def test_known_price_limits(self):
        """既知の値幅制限を確認"""
        # (上限, 値幅) のペアを検証
        expected = {
            100: 30,
            200: 50,
            500: 80,
            700: 100,
            1000: 150,
            1500: 300,
        }
        table_dict = {price: width for price, width in PRICE_LIMIT_TABLE}
        for price, width in expected.items():
            assert table_dict[price] == width
