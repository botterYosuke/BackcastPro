import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath('src'))

from BackcastPro.api.cloud_run_client import CloudRunConfig, CloudRunClient


class TestCloudRunConfig(unittest.TestCase):

    def test_from_environment_with_values(self):
        """環境変数から設定を読み込む"""
        with patch.dict(os.environ, {
            'BACKCASTPRO_GDRIVE_API_URL': 'https://my-api.run.app',
        }, clear=False):
            config = CloudRunConfig.from_environment()
            self.assertEqual(config.api_base_url, 'https://my-api.run.app')
            self.assertTrue(config.is_configured())

    def test_from_environment_defaults(self):
        """環境変数がない場合のデフォルト値"""
        env_backup = {}
        key = 'BACKCASTPRO_GDRIVE_API_URL'
        if key in os.environ:
            env_backup[key] = os.environ.pop(key)

        try:
            config = CloudRunConfig.from_environment()
            self.assertEqual(config.api_base_url, '')
            self.assertFalse(config.is_configured())
        finally:
            os.environ.update(env_backup)

    def test_is_configured_true(self):
        """URLがある場合はTrue"""
        config = CloudRunConfig(api_base_url='https://my-api.run.app')
        self.assertTrue(config.is_configured())

    def test_is_configured_false(self):
        """URLが空の場合はFalse"""
        config = CloudRunConfig(api_base_url='')
        self.assertFalse(config.is_configured())


class TestCloudRunClient(unittest.TestCase):

    def setUp(self):
        self.config = CloudRunConfig(api_base_url='https://my-api.run.app')
        self.client = CloudRunClient(self.config)

    def test_download_file_success(self):
        """ダウンロード成功（200 OK）"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.iter_content.return_value = [b'test content']

        with patch('BackcastPro.api.cloud_run_client.requests.get', return_value=mock_resp):
            with tempfile.NamedTemporaryFile(delete=False) as f:
                test_path = f.name

            try:
                result = self.client.download_file('stocks_daily/1234.duckdb', test_path)
                self.assertTrue(result)
                with open(test_path, 'rb') as f:
                    self.assertEqual(f.read(), b'test content')
            finally:
                if os.path.exists(test_path):
                    os.remove(test_path)

    def test_download_file_not_found(self):
        """ファイルが存在しない場合（404）"""
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch('BackcastPro.api.cloud_run_client.requests.get', return_value=mock_resp):
            with tempfile.NamedTemporaryFile(delete=False) as f:
                test_path = f.name
            os.remove(test_path)

            result = self.client.download_file('stocks_daily/9999.duckdb', test_path)
            self.assertFalse(result)
            self.assertFalse(os.path.exists(test_path))

    def test_download_file_server_error(self):
        """サーバーエラー（500）"""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = Exception("500 Server Error")

        with patch('BackcastPro.api.cloud_run_client.requests.get', return_value=mock_resp):
            with tempfile.NamedTemporaryFile(delete=False) as f:
                test_path = f.name
            os.remove(test_path)

            result = self.client.download_file('stocks_daily/1234.duckdb', test_path)
            self.assertFalse(result)

    def test_download_file_connection_error(self):
        """接続エラー"""
        with patch('BackcastPro.api.cloud_run_client.requests.get',
                    side_effect=Exception("Connection refused")):
            with tempfile.NamedTemporaryFile(delete=False) as f:
                test_path = f.name
            os.remove(test_path)

            result = self.client.download_file('stocks_daily/1234.duckdb', test_path)
            self.assertFalse(result)

    def test_download_file_cleans_up_partial_file(self):
        """ダウンロード失敗時に部分ファイルを削除"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.iter_content.side_effect = Exception("Network interrupted")

        with patch('BackcastPro.api.cloud_run_client.requests.get', return_value=mock_resp):
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(b'partial data')
                test_path = f.name

            result = self.client.download_file('stocks_daily/1234.duckdb', test_path)
            self.assertFalse(result)
            self.assertFalse(os.path.exists(test_path))

    def test_download_file_url_construction(self):
        """URLが正しく構築されること"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.iter_content.return_value = [b'data']

        with patch('BackcastPro.api.cloud_run_client.requests.get', return_value=mock_resp) as mock_get:
            with tempfile.NamedTemporaryFile(delete=False) as f:
                test_path = f.name

            try:
                self.client.download_file('stocks_daily/1234.duckdb', test_path)
                mock_get.assert_called_once_with(
                    'https://my-api.run.app/jp/stocks_daily/1234.duckdb',
                    stream=True,
                    timeout=(10, 300),
                )
            finally:
                if os.path.exists(test_path):
                    os.remove(test_path)

    def test_download_file_url_trailing_slash(self):
        """ベースURLの末尾スラッシュが正しく処理されること"""
        config = CloudRunConfig(api_base_url='https://my-api.run.app/')
        client = CloudRunClient(config)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.iter_content.return_value = [b'data']

        with patch('BackcastPro.api.cloud_run_client.requests.get', return_value=mock_resp) as mock_get:
            with tempfile.NamedTemporaryFile(delete=False) as f:
                test_path = f.name

            try:
                client.download_file('listed_info.duckdb', test_path)
                mock_get.assert_called_once_with(
                    'https://my-api.run.app/jp/listed_info.duckdb',
                    stream=True,
                    timeout=(10, 300),
                )
            finally:
                if os.path.exists(test_path):
                    os.remove(test_path)

    def test_download_stocks_daily(self):
        """download_stocks_daily便利メソッド"""
        with patch.object(self.client, 'download_file', return_value=True) as mock_dl:
            result = self.client.download_stocks_daily('1234', '/local/1234.duckdb')
            self.assertTrue(result)
            mock_dl.assert_called_once_with(
                'stocks_daily/1234.duckdb',
                '/local/1234.duckdb'
            )

    def test_download_stocks_board(self):
        """download_stocks_board便利メソッド"""
        with patch.object(self.client, 'download_file', return_value=True) as mock_dl:
            result = self.client.download_stocks_board('1234', '/local/1234.duckdb')
            self.assertTrue(result)
            mock_dl.assert_called_once_with(
                'stocks_board/1234.duckdb',
                '/local/1234.duckdb'
            )

    def test_download_listed_info(self):
        """download_listed_info便利メソッド"""
        with patch.object(self.client, 'download_file', return_value=True) as mock_dl:
            result = self.client.download_listed_info('/local/listed_info.duckdb')
            self.assertTrue(result)
            mock_dl.assert_called_once_with(
                'listed_info.duckdb',
                '/local/listed_info.duckdb'
            )


if __name__ == '__main__':
    unittest.main()
