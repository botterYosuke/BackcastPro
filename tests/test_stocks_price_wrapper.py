"""
trading_data.stocks_price ラッパーモジュールのテスト
"""

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


class TestStocksPriceValidation:
    """stocks_price の入力検証テスト"""

    @patch("trading_data.stocks_price.db_stocks_daily")
    def test_empty_code_raises(self, mock_db):
        """空の銘柄コードでValueError"""
        from trading_data.stocks_price import stocks_price

        sp = stocks_price()
        with pytest.raises(ValueError, match="銘柄コードが指定されていません"):
            sp.get_japanese_stock_price_data(code="")

    @patch("trading_data.stocks_price.db_stocks_daily")
    def test_none_code_raises(self, mock_db):
        """None銘柄コードでValueError"""
        from trading_data.stocks_price import stocks_price

        sp = stocks_price()
        with pytest.raises(ValueError):
            sp.get_japanese_stock_price_data(code=None)

    @patch("trading_data.stocks_price.db_stocks_daily")
    def test_from_after_to_raises(self, mock_db):
        """開始日が終了日より後でValueError"""
        from trading_data.stocks_price import stocks_price

        sp = stocks_price()
        with pytest.raises(ValueError, match="開始日が終了日より後"):
            sp.get_japanese_stock_price_data(
                code="7203",
                from_=datetime(2024, 12, 31),
                to=datetime(2024, 1, 1),
            )


class TestStocksPriceFallback:
    """stocks_price のフォールバック取得テスト"""

    @patch("trading_data.stocks_price.db_stocks_daily")
    def test_cache_hit_returns_data(self, mock_db_cls):
        """キャッシュにデータがあればそれを返す"""
        from trading_data.stocks_price import stocks_price

        expected_df = pd.DataFrame(
            {"Close": [100.0, 101.0]},
            index=pd.date_range("2024-01-01", periods=2),
        )

        mock_db = MagicMock()
        mock_db.load_stock_prices_from_cache.return_value = expected_df
        mock_db.ensure_db_ready.return_value = None
        mock_db_cls.return_value = mock_db

        sp = stocks_price()
        result = sp.get_japanese_stock_price_data(
            code="7203",
            from_=datetime(2024, 1, 1),
            to=datetime(2024, 1, 2),
        )
        assert not result.empty
        assert len(result) == 2

    @patch("trading_data.stocks_price.stooq_daily_quotes")
    @patch("trading_data.stocks_price.jquants")
    @patch("trading_data.stocks_price.e_api")
    @patch("trading_data.stocks_price.db_stocks_daily")
    def test_all_sources_fail_raises(
        self, mock_db_cls, mock_e_api_cls, mock_jq_cls, mock_stooq
    ):
        """全てのソースが失敗した場合ValueError"""
        from trading_data.stocks_price import stocks_price

        mock_db = MagicMock()
        mock_db.load_stock_prices_from_cache.return_value = None
        mock_db.ensure_db_ready.return_value = None
        mock_db_cls.return_value = mock_db

        mock_e = MagicMock()
        mock_e.isEnable = False
        mock_e_api_cls.return_value = mock_e

        mock_jq = MagicMock()
        mock_jq.isEnable = False
        mock_jq_cls.return_value = mock_jq

        mock_stooq.return_value = pd.DataFrame()

        sp = stocks_price()
        with pytest.raises(ValueError, match="日本株式銘柄の取得に失敗"):
            sp.get_japanese_stock_price_data(
                code="7203",
                from_=datetime(2024, 1, 1),
                to=datetime(2024, 1, 31),
            )


class TestGetStockDaily:
    """get_stock_daily() 関数のテスト"""

    @patch("trading_data.stocks_price.stocks_price")
    def test_returns_datetime_index(self, mock_sp_cls):
        """DatetimeIndexが返される"""
        from trading_data.stocks_price import get_stock_daily

        expected_df = pd.DataFrame(
            {"Close": [100.0, 101.0]},
            index=pd.DatetimeIndex(
                pd.date_range("2024-01-01", periods=2), name="Date"
            ),
        )
        mock_sp = MagicMock()
        mock_sp.get_japanese_stock_price_data.return_value = expected_df
        mock_sp_cls.return_value = mock_sp

        result = get_stock_daily("7203")
        assert isinstance(result.index, pd.DatetimeIndex)

    @patch("trading_data.stocks_price.stocks_price")
    def test_date_column_converted_to_index(self, mock_sp_cls):
        """Date列がインデックスに変換される"""
        from trading_data.stocks_price import get_stock_daily

        df_with_date = pd.DataFrame({
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "Close": [100.0, 101.0],
        })
        mock_sp = MagicMock()
        mock_sp.get_japanese_stock_price_data.return_value = df_with_date
        mock_sp_cls.return_value = mock_sp

        result = get_stock_daily("7203")
        assert isinstance(result.index, pd.DatetimeIndex)
