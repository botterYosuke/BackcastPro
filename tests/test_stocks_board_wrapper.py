"""
trading_data.stocks_board ラッパーモジュールのテスト
"""

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


class TestStocksBoardValidation:
    """stocks_board の入力検証テスト"""

    @patch("trading_data.stocks_board.db_stocks_board")
    def test_empty_code_raises(self, mock_db_cls):
        """空の銘柄コードでValueError"""
        from trading_data.stocks_board import stocks_board

        mock_db_cls.return_value = MagicMock()
        sb = stocks_board()
        with pytest.raises(ValueError, match="銘柄コードが指定されていません"):
            sb.get_japanese_stock_board_data(code="")

    @patch("trading_data.stocks_board.db_stocks_board")
    def test_none_code_raises(self, mock_db_cls):
        """None銘柄コードでValueError"""
        from trading_data.stocks_board import stocks_board

        mock_db_cls.return_value = MagicMock()
        sb = stocks_board()
        with pytest.raises(ValueError):
            sb.get_japanese_stock_board_data(code=None)


class TestStocksBoardDateQuery:
    """日時指定の板情報取得テスト"""

    @patch("trading_data.stocks_board.db_stocks_board")
    def test_date_specified_returns_cached(self, mock_db_cls):
        """日時指定でキャッシュから取得"""
        from trading_data.stocks_board import stocks_board

        cached_df = pd.DataFrame({
            "Price": [1000.0, 1001.0],
            "Qty": [100, 200],
            "Type": ["Bid", "Ask"],
        })
        mock_db = MagicMock()
        mock_db.ensure_db_ready.return_value = None
        mock_db.load_stock_board_from_cache.return_value = cached_df
        mock_db_cls.return_value = mock_db

        sb = stocks_board()
        result = sb.get_japanese_stock_board_data(
            code="8306", date=datetime(2024, 1, 15, 10, 0)
        )
        assert not result.empty

    @patch("trading_data.stocks_board.db_stocks_board")
    def test_date_specified_no_cache_raises(self, mock_db_cls):
        """日時指定でキャッシュなしはValueError"""
        from trading_data.stocks_board import stocks_board

        mock_db = MagicMock()
        mock_db.ensure_db_ready.return_value = None
        mock_db.load_stock_board_from_cache.return_value = pd.DataFrame()
        mock_db_cls.return_value = mock_db

        sb = stocks_board()
        with pytest.raises(ValueError, match="板情報の取得に失敗"):
            sb.get_japanese_stock_board_data(
                code="8306", date=datetime(2024, 1, 15, 10, 0)
            )


class TestStocksBoardFallback:
    """板情報のフォールバック取得テスト"""

    @patch("trading_data.stocks_board.kabusap")
    @patch("trading_data.stocks_board.db_stocks_board")
    def test_kabu_station_success(self, mock_db_cls, mock_kabusap_cls):
        """kabuステーションからの取得成功"""
        from trading_data.stocks_board import stocks_board

        board_df = pd.DataFrame({
            "Price": [1000.0, 1001.0],
            "Qty": [100, 200],
            "Type": ["Bid", "Ask"],
        })
        mock_kabu = MagicMock()
        mock_kabu.isEnable = True
        mock_kabu.get_board.return_value = board_df
        mock_kabusap_cls.return_value = mock_kabu

        mock_db = MagicMock()
        mock_db.ensure_db_ready.return_value = None
        mock_db_cls.return_value = mock_db

        sb = stocks_board()
        result = sb.get_japanese_stock_board_data(code="8306")
        assert not result.empty

    @patch("trading_data.stocks_board.e_api")
    @patch("trading_data.stocks_board.kabusap")
    @patch("trading_data.stocks_board.db_stocks_board")
    def test_fallback_to_e_shiten(self, mock_db_cls, mock_kabusap_cls, mock_e_api_cls):
        """kabuステーション失敗 → 立花証券にフォールバック"""
        from trading_data.stocks_board import stocks_board

        board_df = pd.DataFrame({
            "Price": [1000.0, 1001.0],
            "Qty": [100, 200],
            "Type": ["Bid", "Ask"],
        })

        mock_kabu = MagicMock()
        mock_kabu.isEnable = False
        mock_kabusap_cls.return_value = mock_kabu

        mock_e = MagicMock()
        mock_e.isEnable = True
        mock_e.get_board.return_value = board_df
        mock_e_api_cls.return_value = mock_e

        mock_db = MagicMock()
        mock_db.ensure_db_ready.return_value = None
        mock_db_cls.return_value = mock_db

        sb = stocks_board()
        result = sb.get_japanese_stock_board_data(code="8306")
        assert not result.empty

    @patch("trading_data.stocks_board.e_api")
    @patch("trading_data.stocks_board.kabusap")
    @patch("trading_data.stocks_board.db_stocks_board")
    def test_all_sources_fail_raises(
        self, mock_db_cls, mock_kabusap_cls, mock_e_api_cls
    ):
        """全てのソースが失敗した場合ValueError"""
        from trading_data.stocks_board import stocks_board

        mock_kabu = MagicMock()
        mock_kabu.isEnable = False
        mock_kabusap_cls.return_value = mock_kabu

        mock_e = MagicMock()
        mock_e.isEnable = False
        mock_e_api_cls.return_value = mock_e

        mock_db = MagicMock()
        mock_db.ensure_db_ready.return_value = None
        mock_db_cls.return_value = mock_db

        sb = stocks_board()
        with pytest.raises(ValueError, match="板情報の取得に失敗"):
            sb.get_japanese_stock_board_data(code="8306")
