import unittest
from unittest.mock import patch, MagicMock
import os
import shutil
import sys
import logging

import pandas as pd

# Ensure src is in pythonpath
sys.path.insert(0, os.path.abspath("src"))

from BackcastPro.api.db_stocks_info import db_stocks_info


class TestDbStocksInfo(unittest.TestCase):
    def setUp(self):
        # Set cache dir to a temp path to avoid cluttering unrelated dirs
        self.test_cache_dir = os.path.abspath("test_cache_db_stocks_info")
        os.environ["STOCKDATA_CACHE_DIR"] = self.test_cache_dir

        # Initialize the class under test
        self.db_info = db_stocks_info()

    def tearDown(self):
        # Remove the temporary cache directory
        if os.path.exists(self.test_cache_dir):
            try:
                shutil.rmtree(self.test_cache_dir)
            except Exception:
                pass

        # Unset the env var
        if "STOCKDATA_CACHE_DIR" in os.environ:
            del os.environ["STOCKDATA_CACHE_DIR"]

    def test_download_from_cloud_success(self):
        """Test successful download from Cloud Run"""
        with patch(
            "BackcastPro.api.cloud_run_client.CloudRunClient"
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.config.is_configured.return_value = True
            mock_client.download_file.return_value = True

            test_path = os.path.join(self.test_cache_dir, "test_downloaded.duckdb")
            os.makedirs(os.path.dirname(test_path), exist_ok=True)

            result = self.db_info._download_from_cloud(test_path)

            self.assertTrue(result, "Download should return True on success")
            mock_client.download_file.assert_called_once_with(
                "jp/listed_info.duckdb", test_path
            )

    def test_download_from_cloud_failure(self):
        """Test failure during Cloud Run download"""
        with patch(
            "BackcastPro.api.cloud_run_client.CloudRunClient"
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.config.is_configured.return_value = True
            mock_client.download_file.return_value = False

            test_path = os.path.join(self.test_cache_dir, "test_fail.duckdb")

            result = self.db_info._download_from_cloud(test_path)

            self.assertFalse(result, "Download should return False on failure")

    def test_download_from_cloud_not_configured(self):
        """Test behavior when Cloud Run is not configured"""
        with patch(
            "BackcastPro.api.cloud_run_client.CloudRunClient"
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.config.is_configured.return_value = False

            test_path = os.path.join(self.test_cache_dir, "test_notconfigured.duckdb")

            result = self.db_info._download_from_cloud(test_path)

            self.assertFalse(result, "Download should return False if not configured")


class TestSaveListedInfoColumnValidation(unittest.TestCase):
    """save_listed_info() の必須カラムバリデーションテスト"""

    def setUp(self):
        self.test_cache_dir = os.path.abspath("test_cache_save_listed_info")
        os.environ["STOCKDATA_CACHE_DIR"] = self.test_cache_dir
        self.db_info = db_stocks_info()

    def tearDown(self):
        if os.path.exists(self.test_cache_dir):
            try:
                shutil.rmtree(self.test_cache_dir)
            except Exception:
                pass
        if "STOCKDATA_CACHE_DIR" in os.environ:
            del os.environ["STOCKDATA_CACHE_DIR"]

    def _make_v2_api_dataframe(self) -> pd.DataFrame:
        """J-Quants V2 API の実際のレスポンス形式（短縮カラム名）を再現"""
        return pd.DataFrame({
            "Date": ["2025-01-06"],
            "Code": ["7203"],
            "CoName": ["トヨタ自動車"],
            "CoNameEn": ["TOYOTA MOTOR CORPORATION"],
            "S17": ["7"],
            "S17Nm": ["自動車・輸送機"],
            "S33": ["15"],
            "S33Nm": ["輸送用機器"],
            "ScaleCat": ["TOPIX Large70"],
            "Mkt": ["0111"],
            "MktNm": ["プライム"],
            "Mrgn": ["1"],
            "MrgnNm": ["貸借"],
            "source": ["j-quants"],
        })

    def _make_expected_dataframe(self) -> pd.DataFrame:
        """save_listed_info() が期待する長いカラム名の DataFrame"""
        return pd.DataFrame({
            "Date": ["2025-01-06"],
            "Code": ["7203"],
            "CompanyName": ["トヨタ自動車"],
            "CompanyNameEnglish": ["TOYOTA MOTOR CORPORATION"],
            "Sector17Code": ["7"],
            "Sector17CodeName": ["自動車・輸送機"],
            "Sector33Code": ["15"],
            "Sector33CodeName": ["輸送用機器"],
            "ScaleCategory": ["TOPIX Large70"],
            "MarketCode": ["0111"],
            "MarketCodeName": ["プライム"],
        })

    def test_v2_api_response_missing_required_columns(self):
        """
        J-Quants V2 API の短縮カラム名では save_listed_info() の
        必須カラムチェックに引っかかり、保存がスキップされることを確認する。

        V2 API は CoName, CoNameEn, S17, S17Nm, S33, S33Nm, ScaleCat, Mkt, MktNm
        を返すが、save_listed_info() は CompanyName, CompanyNameEnglish,
        Sector17Code, Sector17CodeName, Sector33Code, Sector33CodeName,
        ScaleCategory, MarketCode, MarketCodeName を期待する。
        """
        df_v2 = self._make_v2_api_dataframe()

        with self.assertLogs("BackcastPro.api.db_stocks_info", level="WARNING") as cm:
            self.db_info.save_listed_info(df_v2)

        # "必須カラムが不足しています" の警告が出ることを確認
        warning_messages = [log for log in cm.output if "必須カラムが不足しています" in log]
        self.assertTrue(
            len(warning_messages) > 0,
            "V2 API の短縮カラム名では必須カラム不足の警告が出るべき",
        )

        # 不足カラム名が警告メッセージに含まれていることを確認
        warning_text = warning_messages[0]
        expected_missing = [
            "CompanyName", "CompanyNameEnglish",
            "Sector17Code", "Sector17CodeName",
            "Sector33Code", "Sector33CodeName",
            "ScaleCategory", "MarketCode", "MarketCodeName",
        ]
        for col in expected_missing:
            self.assertIn(
                col, warning_text,
                f"不足カラム '{col}' が警告メッセージに含まれるべき",
            )

    def test_v2_api_response_data_not_saved(self):
        """
        V2 API レスポンスを渡すと保存がスキップされ、
        キャッシュからデータを読み込めないことを確認する。
        """
        df_v2 = self._make_v2_api_dataframe()

        # save はスキップされる（警告のみ）
        self.db_info.save_listed_info(df_v2)

        # キャッシュは空であるべき
        cached = self.db_info.load_listed_info_from_cache()
        self.assertTrue(cached.empty, "V2 カラム名のデータは保存されないためキャッシュは空")

    def test_expected_columns_save_succeeds(self):
        """
        正しいカラム名の DataFrame は正常に保存・読み込みできることを確認する。
        """
        df_expected = self._make_expected_dataframe()

        # 保存が成功する
        self.db_info.save_listed_info(df_expected)

        # キャッシュから読み込める
        cached = self.db_info.load_listed_info_from_cache()
        self.assertFalse(cached.empty, "正しいカラム名のデータは保存され読み込めるべき")
        self.assertEqual(len(cached), 1)
        self.assertEqual(cached.iloc[0]["Code"], "7203")
        self.assertEqual(cached.iloc[0]["CompanyName"], "トヨタ自動車")

    def test_jquants_renames_v2_short_columns(self):
        """
        jquants.get_listed_info() が V2 API の短縮カラム名を
        save_listed_info() が期待する正規カラム名にリネームすることを確認する。
        """
        from trading_data.lib.jquants import jquants

        # シングルトンリセット
        jquants._instance = None
        os.environ["JQUANTS_API_KEY"] = "dummy-key"

        try:
            jq = jquants()

            # V2 API の実際のレスポンス形式を模擬
            def fake_get_all_pages(endpoint, params):
                return [{
                    "Date": "2025-01-06",
                    "Code": "72030",
                    "CoName": "トヨタ自動車",
                    "CoNameEn": "TOYOTA MOTOR CORPORATION",
                    "S17": "7",
                    "S17Nm": "自動車・輸送機",
                    "S33": "15",
                    "S33Nm": "輸送用機器",
                    "ScaleCat": "TOPIX Large70",
                    "Mkt": "0111",
                    "MktNm": "プライム",
                    "Mrgn": "1",
                    "MrgnNm": "貸借",
                }]

            jq._get_all_pages = fake_get_all_pages

            df = jq.get_listed_info(code="7203")

            # 短縮カラム名がリネームされていることを確認
            expected_renames = {
                "CompanyName": "トヨタ自動車",
                "CompanyNameEnglish": "TOYOTA MOTOR CORPORATION",
                "Sector17Code": "7",
                "Sector17CodeName": "自動車・輸送機",
                "Sector33Code": "15",
                "Sector33CodeName": "輸送用機器",
                "ScaleCategory": "TOPIX Large70",
                "MarketCode": "0111",
                "MarketCodeName": "プライム",
            }
            for col, expected_val in expected_renames.items():
                self.assertIn(col, df.columns, f"カラム '{col}' が存在すべき")
                self.assertEqual(df.iloc[0][col], expected_val)

            # 短縮カラム名は残っていないことを確認
            short_names = ["CoName", "CoNameEn", "S17", "S17Nm", "S33", "S33Nm",
                           "ScaleCat", "Mkt", "MktNm"]
            for short in short_names:
                self.assertNotIn(short, df.columns,
                                 f"短縮カラム名 '{short}' はリネーム後に残らないべき")

        finally:
            jquants._instance = None
            if "JQUANTS_API_KEY" in os.environ:
                del os.environ["JQUANTS_API_KEY"]

    def test_v2_response_saves_to_db_after_rename(self):
        """
        V2 API レスポンスが jquants.get_listed_info() でリネームされた後、
        save_listed_info() で正常に保存できることを確認する（E2E）。
        """
        from trading_data.lib.jquants import jquants

        jquants._instance = None
        os.environ["JQUANTS_API_KEY"] = "dummy-key"

        try:
            jq = jquants()

            def fake_get_all_pages(endpoint, params):
                return [{
                    "Date": "2025-01-06",
                    "Code": "72030",
                    "CoName": "トヨタ自動車",
                    "CoNameEn": "TOYOTA MOTOR CORPORATION",
                    "S17": "7",
                    "S17Nm": "自動車・輸送機",
                    "S33": "15",
                    "S33Nm": "輸送用機器",
                    "ScaleCat": "TOPIX Large70",
                    "Mkt": "0111",
                    "MktNm": "プライム",
                    "Mrgn": "1",
                    "MrgnNm": "貸借",
                }]

            jq._get_all_pages = fake_get_all_pages

            df = jq.get_listed_info(code="7203")
            # stocks_info._fetch_from_jquants と同じ処理
            df['Code'] = df['Code'].str[:4]

            # save_listed_info で保存できる
            self.db_info.save_listed_info(df)

            # キャッシュから読み込める
            cached = self.db_info.load_listed_info_from_cache()
            self.assertFalse(cached.empty, "V2 レスポンスがリネーム後に保存・読み込みできるべき")
            self.assertEqual(cached.iloc[0]["Code"], "7203")
            self.assertEqual(cached.iloc[0]["CompanyName"], "トヨタ自動車")
            self.assertEqual(cached.iloc[0]["Sector17CodeName"], "自動車・輸送機")

        finally:
            jquants._instance = None
            if "JQUANTS_API_KEY" in os.environ:
                del os.environ["JQUANTS_API_KEY"]


if __name__ == "__main__":
    unittest.main()
