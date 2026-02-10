import unittest
from unittest.mock import patch, MagicMock
import os
import shutil
import sys

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


if __name__ == "__main__":
    unittest.main()
