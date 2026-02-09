"""
kabuステーションAPI Client (kabusap.py) のテスト
"""

import json
import os

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from trading_data.lib.kabusap import kabusap


@pytest.fixture(autouse=True)
def reset_singleton():
    """各テスト前にシングルトンをリセット"""
    kabusap._instance = None
    yield
    kabusap._instance = None


class TestKabusapSingleton:
    """シングルトンパターンのテスト"""

    def test_singleton_returns_same_instance(self):
        """同じインスタンスが返される"""
        with patch.dict(os.environ, {"KABUSAP_API_PASSWORD": ""}, clear=False):
            k1 = kabusap()
            k2 = kabusap()
            assert k1 is k2

    def test_initialized_flag(self):
        """_initialized フラグが設定される"""
        with patch.dict(os.environ, {"KABUSAP_API_PASSWORD": ""}, clear=False):
            k = kabusap()
            assert k._initialized is True


class TestSetToken:
    """_set_token() のテスト"""

    def test_no_password_returns_false(self):
        """パスワード未設定でFalse"""
        with patch.dict(os.environ, {}, clear=True):
            # dotenvも無効化
            os.environ.pop("KABUSAP_API_PASSWORD", None)
            k = kabusap()
            assert k.isEnable is False

    @patch("trading_data.lib.kabusap.urllib.request.urlopen")
    def test_successful_token(self, mock_urlopen):
        """トークン取得成功"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {"ResultCode": 0, "Token": "test-token-123"}
        ).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        with patch.dict(
            os.environ, {"KABUSAP_API_PASSWORD": "test_pass"}, clear=False
        ):
            k = kabusap()
            assert k.isEnable is True
            assert k.api_key == "test-token-123"
            assert k.headers["X-API-KEY"] == "test-token-123"

    @patch("trading_data.lib.kabusap.urllib.request.urlopen")
    def test_token_no_token_in_response(self, mock_urlopen):
        """レスポンスにTokenがない場合"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {"ResultCode": 1, "Message": "Invalid password"}
        ).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        with patch.dict(
            os.environ, {"KABUSAP_API_PASSWORD": "wrong_pass"}, clear=False
        ):
            k = kabusap()
            assert k.isEnable is False

    @patch("trading_data.lib.kabusap.urllib.request.urlopen")
    def test_token_connection_error(self, mock_urlopen):
        """接続エラー"""
        mock_urlopen.side_effect = Exception("Connection refused")

        with patch.dict(
            os.environ, {"KABUSAP_API_PASSWORD": "test_pass"}, clear=False
        ):
            k = kabusap()
            assert k.isEnable is False


class TestRefreshToken:
    """_refresh_token_if_needed() のテスト"""

    def test_refresh_not_needed_when_key_exists(self):
        """api_keyが存在する場合はリフレッシュ不要"""
        with patch.dict(os.environ, {"KABUSAP_API_PASSWORD": ""}, clear=False):
            k = kabusap()
            k.api_key = "existing-token"
            assert k._refresh_token_if_needed() is True

    def test_refresh_needed_when_key_empty(self):
        """api_keyが空の場合はリフレッシュ試行"""
        with patch.dict(os.environ, {"KABUSAP_API_PASSWORD": ""}, clear=False):
            k = kabusap()
            k.api_key = ""
            with patch.object(k, "_set_token", return_value=False):
                result = k._refresh_token_if_needed()
                assert result is False


class TestGetBoard:
    """get_board() のテスト"""

    def test_not_enabled_returns_empty(self):
        """API無効時は空のDataFrame"""
        with patch.dict(os.environ, {"KABUSAP_API_PASSWORD": ""}, clear=False):
            k = kabusap()
            k.isEnable = False
            result = k.get_board("8306")
            assert isinstance(result, pd.DataFrame)
            assert result.empty

    def test_empty_code_returns_empty(self):
        """空の銘柄コードは空のDataFrame"""
        with patch.dict(os.environ, {"KABUSAP_API_PASSWORD": ""}, clear=False):
            k = kabusap()
            k.isEnable = True
            result = k.get_board("")
            assert result.empty

    def test_none_code_returns_empty(self):
        """None銘柄コードは空のDataFrame"""
        with patch.dict(os.environ, {"KABUSAP_API_PASSWORD": ""}, clear=False):
            k = kabusap()
            k.isEnable = True
            result = k.get_board(None)
            assert result.empty

    @patch("trading_data.lib.kabusap.urllib.request.urlopen")
    def test_successful_board_buy_sell_format(self, mock_urlopen):
        """Buy/Sell形式の板情報取得"""
        response_data = {
            "Buy1": {"Price": 1000.0, "Qty": 100},
            "Buy2": {"Price": 999.0, "Qty": 200},
            "Sell1": {"Price": 1001.0, "Qty": 150},
            "Sell2": {"Price": 1002.0, "Qty": 250},
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        with patch.dict(os.environ, {"KABUSAP_API_PASSWORD": ""}, clear=False):
            k = kabusap()
            k.isEnable = True
            k.api_key = "test-token"
            df = k.get_board("8306")

            assert isinstance(df, pd.DataFrame)
            assert not df.empty
            assert "Price" in df.columns
            assert "Qty" in df.columns
            assert "Type" in df.columns
            assert set(df["Type"].unique()) == {"Bid", "Ask"}

    @patch("trading_data.lib.kabusap.urllib.request.urlopen")
    def test_board_api_error(self, mock_urlopen):
        """APIエラー時は空のDataFrame"""
        response_data = {"ResultCode": 4, "Message": "Invalid code"}
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        with patch.dict(os.environ, {"KABUSAP_API_PASSWORD": ""}, clear=False):
            k = kabusap()
            k.isEnable = True
            k.api_key = "test-token"
            df = k.get_board("9999")
            assert df.empty

    @patch("trading_data.lib.kabusap.urllib.request.urlopen")
    def test_board_connection_error(self, mock_urlopen):
        """接続エラー時は空のDataFrame"""
        mock_urlopen.side_effect = Exception("Connection refused")

        with patch.dict(os.environ, {"KABUSAP_API_PASSWORD": ""}, clear=False):
            k = kabusap()
            k.isEnable = True
            k.api_key = "test-token"
            df = k.get_board("8306")
            assert df.empty
