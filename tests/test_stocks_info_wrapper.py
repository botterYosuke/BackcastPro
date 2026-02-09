"""
trading_data.stocks_info ラッパーモジュールのテスト
"""

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock


class TestStocksInfoFetchFromJquants:
    """stocks_info._fetch_from_jquants() のテスト"""

    @patch("trading_data.stocks_info.db_stocks_info")
    @patch("trading_data.stocks_info.jquants")
    def test_disabled_jquants_returns_none(self, mock_jq_cls, mock_db_cls):
        """J-Quantsが無効の場合Noneを返す"""
        from trading_data.stocks_info import stocks_info

        mock_jq = MagicMock()
        mock_jq.isEnable = False
        mock_jq_cls.return_value = mock_jq
        mock_db_cls.return_value = MagicMock()

        si = stocks_info()
        result = si._fetch_from_jquants(code="7203")
        assert result is None

    @patch("trading_data.stocks_info.db_stocks_info")
    @patch("trading_data.stocks_info.jquants")
    def test_successful_fetch_truncates_code(self, mock_jq_cls, mock_db_cls):
        """取得成功時にCodeを4文字に切り詰める"""
        from trading_data.stocks_info import stocks_info

        mock_jq = MagicMock()
        mock_jq.isEnable = True
        mock_jq.get_listed_info.return_value = pd.DataFrame({
            "Code": ["72030"],
            "CompanyName": ["トヨタ自動車"],
        })
        mock_jq_cls.return_value = mock_jq
        mock_db_cls.return_value = MagicMock()

        si = stocks_info()
        result = si._fetch_from_jquants(code="7203")
        assert result is not None
        assert result.iloc[0]["Code"] == "7203"

    @patch("trading_data.stocks_info.db_stocks_info")
    @patch("trading_data.stocks_info.jquants")
    def test_empty_result_returns_none(self, mock_jq_cls, mock_db_cls):
        """空の結果はNoneを返す"""
        from trading_data.stocks_info import stocks_info

        mock_jq = MagicMock()
        mock_jq.isEnable = True
        mock_jq.get_listed_info.return_value = pd.DataFrame()
        mock_jq_cls.return_value = mock_jq
        mock_db_cls.return_value = MagicMock()

        si = stocks_info()
        result = si._fetch_from_jquants(code="9999")
        assert result is None


class TestGetCompanyName:
    """stocks_info.get_company_name() のテスト"""

    @patch("trading_data.stocks_info.db_stocks_info")
    @patch("trading_data.stocks_info.jquants")
    def test_disabled_jquants_returns_code(self, mock_jq_cls, mock_db_cls):
        """J-Quants無効時は銘柄コードを返す"""
        from trading_data.stocks_info import stocks_info

        mock_jq = MagicMock()
        mock_jq.isEnable = False
        mock_jq_cls.return_value = mock_jq
        mock_db_cls.return_value = MagicMock()

        si = stocks_info()
        result = si.get_company_name("7203")
        assert result == "7203"

    @patch("trading_data.stocks_info.db_stocks_info")
    @patch("trading_data.stocks_info.jquants")
    def test_successful_name_retrieval(self, mock_jq_cls, mock_db_cls):
        """正常に銘柄名称を取得"""
        from trading_data.stocks_info import stocks_info

        mock_jq = MagicMock()
        mock_jq.isEnable = True
        mock_jq.get_listed_info.return_value = pd.DataFrame({
            "Code": ["72030"],
            "CompanyName": ["トヨタ自動車"],
        })
        mock_jq_cls.return_value = mock_jq
        mock_db_cls.return_value = MagicMock()

        si = stocks_info()
        result = si.get_company_name("7203")
        assert result == "トヨタ自動車"

    @patch("trading_data.stocks_info.db_stocks_info")
    @patch("trading_data.stocks_info.jquants")
    def test_api_error_returns_code(self, mock_jq_cls, mock_db_cls):
        """APIエラー時は銘柄コードを返す"""
        from trading_data.stocks_info import stocks_info

        mock_jq = MagicMock()
        mock_jq.isEnable = True
        mock_jq.get_listed_info.side_effect = Exception("API Error")
        mock_jq_cls.return_value = mock_jq
        mock_db_cls.return_value = MagicMock()

        si = stocks_info()
        result = si.get_company_name("7203")
        assert result == "7203"

    @patch("trading_data.stocks_info.db_stocks_info")
    @patch("trading_data.stocks_info.jquants")
    def test_code_with_suffix_stripped(self, mock_jq_cls, mock_db_cls):
        """サフィックス付きコードが処理される"""
        from trading_data.stocks_info import stocks_info

        mock_jq = MagicMock()
        mock_jq.isEnable = True
        mock_jq.get_listed_info.return_value = pd.DataFrame({
            "Code": ["72030"],
            "CompanyName": ["トヨタ自動車"],
        })
        mock_jq_cls.return_value = mock_jq
        mock_db_cls.return_value = MagicMock()

        si = stocks_info()
        result = si.get_company_name("7203.JP")
        # get_listed_infoが"7203"で呼ばれることを確認
        mock_jq.get_listed_info.assert_called_with(code="7203")
        assert result == "トヨタ自動車"


class TestStocksInfoGetJapaneseListed:
    """stocks_info.get_japanese_listed_info() のテスト"""

    @patch("trading_data.stocks_info.db_stocks_info")
    @patch("trading_data.stocks_info.jquants")
    def test_jquants_success_saves_to_db(self, mock_jq_cls, mock_db_cls):
        """J-Quants成功時にDBに保存"""
        from trading_data.stocks_info import stocks_info

        mock_jq = MagicMock()
        mock_jq.isEnable = True
        mock_jq.get_listed_info.return_value = pd.DataFrame({
            "Code": ["72030"],
            "CompanyName": ["トヨタ自動車"],
        })
        mock_jq_cls.return_value = mock_jq

        mock_db = MagicMock()
        mock_db.ensure_db_ready.return_value = None
        mock_db_cls.return_value = mock_db

        si = stocks_info()
        result = si.get_japanese_listed_info(code="7203")
        assert not result.empty

    @patch("trading_data.stocks_info.db_stocks_info")
    @patch("trading_data.stocks_info.jquants")
    def test_fallback_to_cache(self, mock_jq_cls, mock_db_cls):
        """J-Quants失敗時にキャッシュにフォールバック"""
        from trading_data.stocks_info import stocks_info

        mock_jq = MagicMock()
        mock_jq.isEnable = False
        mock_jq_cls.return_value = mock_jq

        cached_df = pd.DataFrame({
            "Code": ["7203"],
            "CompanyName": ["トヨタ自動車"],
        })
        mock_db = MagicMock()
        mock_db.ensure_db_ready.return_value = None
        mock_db.load_listed_info_from_cache.return_value = cached_df
        mock_db_cls.return_value = mock_db

        si = stocks_info()
        result = si.get_japanese_listed_info(code="7203")
        assert not result.empty

    @patch("trading_data.stocks_info.db_stocks_info")
    @patch("trading_data.stocks_info.jquants")
    def test_all_fail_raises(self, mock_jq_cls, mock_db_cls):
        """全てのソースが失敗した場合ValueError"""
        from trading_data.stocks_info import stocks_info

        mock_jq = MagicMock()
        mock_jq.isEnable = False
        mock_jq_cls.return_value = mock_jq

        mock_db = MagicMock()
        mock_db.ensure_db_ready.return_value = None
        mock_db.load_listed_info_from_cache.return_value = pd.DataFrame()
        mock_db_cls.return_value = mock_db

        si = stocks_info()
        with pytest.raises(ValueError, match="日本株式上場銘柄一覧の取得に失敗"):
            si.get_japanese_listed_info(code="9999")
