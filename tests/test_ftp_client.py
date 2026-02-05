import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath('src'))

from BackcastPro.api.ftp_client import FTPConfig, FTPClient


class TestFTPConfig(unittest.TestCase):

    def test_from_environment_with_values(self):
        """環境変数から設定を読み込む"""
        with patch.dict(os.environ, {
            'BACKCASTPRO_FTP_HOST': 'test.host.com',
            'BACKCASTPRO_FTP_PORT': '2121',
            'BACKCASTPRO_FTP_USER': 'testuser',
            'BACKCASTPRO_FTP_PASSWORD': 'testpass',
        }, clear=False):
            config = FTPConfig.from_environment()
            self.assertEqual(config.host, 'test.host.com')
            self.assertEqual(config.port, 2121)
            self.assertEqual(config.username, 'testuser')
            self.assertEqual(config.password, 'testpass')
            self.assertTrue(config.is_configured())

    def test_from_environment_defaults(self):
        """環境変数がない場合のデフォルト値"""
        with patch.dict(os.environ, {
            'BACKCASTPRO_FTP_HOST': '',
            'BACKCASTPRO_FTP_PORT': '',
            'BACKCASTPRO_FTP_USER': '',
            'BACKCASTPRO_FTP_PASSWORD': '',
        }, clear=False):
            # Clear relevant env vars
            env_backup = {}
            for key in ['BACKCASTPRO_FTP_HOST', 'BACKCASTPRO_FTP_PORT',
                       'BACKCASTPRO_FTP_USER', 'BACKCASTPRO_FTP_PASSWORD']:
                if key in os.environ:
                    env_backup[key] = os.environ.pop(key)

            try:
                config = FTPConfig.from_environment()
                self.assertEqual(config.host, 'backcast.i234.me')
                self.assertEqual(config.port, 21)
                self.assertFalse(config.is_configured())
            finally:
                os.environ.update(env_backup)

    def test_is_configured_true(self):
        """認証情報がある場合はTrue"""
        config = FTPConfig(
            host='test.host.com',
            port=21,
            username='user',
            password='pass'
        )
        self.assertTrue(config.is_configured())

    def test_is_configured_false_no_user(self):
        """ユーザー名がない場合はFalse"""
        config = FTPConfig(
            host='test.host.com',
            port=21,
            username='',
            password='pass'
        )
        self.assertFalse(config.is_configured())

    def test_is_configured_false_no_password(self):
        """パスワードがない場合はFalse"""
        config = FTPConfig(
            host='test.host.com',
            port=21,
            username='user',
            password=''
        )
        self.assertFalse(config.is_configured())


class TestFTPClient(unittest.TestCase):

    def setUp(self):
        self.config = FTPConfig(
            host='test.host.com',
            port=21,
            username='testuser',
            password='testpass'
        )
        self.client = FTPClient(self.config)

    def test_download_file_success(self):
        """ダウンロード成功"""
        with patch('ftplib.FTP') as mock_ftp_cls:
            mock_ftp = mock_ftp_cls.return_value
            mock_ftp.__enter__.return_value = mock_ftp

            mock_ftp.connect.return_value = None
            mock_ftp.login.return_value = None
            mock_ftp.voidcmd.return_value = "200 Type set to I"
            mock_ftp.size.return_value = 1024

            def side_effect_retrbinary(cmd, callback):
                callback(b'test content')
            mock_ftp.retrbinary.side_effect = side_effect_retrbinary

            with tempfile.NamedTemporaryFile(delete=False) as f:
                test_path = f.name

            try:
                result = self.client.download_file('/remote/test.db', test_path)
                self.assertTrue(result)
                with open(test_path, 'rb') as f:
                    self.assertEqual(f.read(), b'test content')
            finally:
                if os.path.exists(test_path):
                    os.remove(test_path)

    def test_download_file_not_found(self):
        """リモートファイルが存在しない場合"""
        with patch('ftplib.FTP') as mock_ftp_cls:
            mock_ftp = mock_ftp_cls.return_value
            mock_ftp.__enter__.return_value = mock_ftp

            mock_ftp.connect.return_value = None
            mock_ftp.login.return_value = None
            mock_ftp.voidcmd.return_value = "200 Type set to I"
            mock_ftp.size.side_effect = Exception("File not found")

            with tempfile.NamedTemporaryFile(delete=False) as f:
                test_path = f.name
            os.remove(test_path)

            result = self.client.download_file('/remote/notexist.db', test_path)
            self.assertFalse(result)
            self.assertFalse(os.path.exists(test_path))

    def test_download_file_connection_error(self):
        """接続エラー"""
        with patch('ftplib.FTP') as mock_ftp_cls:
            mock_ftp = mock_ftp_cls.return_value
            mock_ftp.__enter__.return_value = mock_ftp
            mock_ftp.connect.side_effect = Exception("Connection refused")

            with tempfile.NamedTemporaryFile(delete=False) as f:
                test_path = f.name
            os.remove(test_path)

            result = self.client.download_file('/remote/test.db', test_path)
            self.assertFalse(result)

    def test_upload_file_success(self):
        """アップロード成功"""
        with patch('ftplib.FTP') as mock_ftp_cls:
            mock_ftp = mock_ftp_cls.return_value
            mock_ftp.__enter__.return_value = mock_ftp

            mock_ftp.connect.return_value = None
            mock_ftp.login.return_value = None
            mock_ftp.set_pasv.return_value = None
            mock_ftp.cwd.return_value = None
            mock_ftp.storbinary.return_value = None

            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(b'upload content')
                test_path = f.name

            try:
                result = self.client.upload_file(test_path, '/remote/dir/test.db')
                self.assertTrue(result)
                mock_ftp.storbinary.assert_called_once()
            finally:
                if os.path.exists(test_path):
                    os.remove(test_path)

    def test_download_stocks_daily(self):
        """download_stocks_daily便利メソッド"""
        with patch.object(self.client, 'download_file', return_value=True) as mock_download:
            result = self.client.download_stocks_daily('1234', '/local/1234.duckdb')
            self.assertTrue(result)
            mock_download.assert_called_once_with(
                '/StockData/jp/stocks_daily/1234.duckdb',
                '/local/1234.duckdb'
            )

    def test_download_stocks_board(self):
        """download_stocks_board便利メソッド"""
        with patch.object(self.client, 'download_file', return_value=True) as mock_download:
            result = self.client.download_stocks_board('1234', '/local/1234.duckdb')
            self.assertTrue(result)
            mock_download.assert_called_once_with(
                '/StockData/jp/stocks_board/1234.duckdb',
                '/local/1234.duckdb'
            )

    def test_download_listed_info(self):
        """download_listed_info便利メソッド"""
        with patch.object(self.client, 'download_file', return_value=True) as mock_download:
            result = self.client.download_listed_info('/local/listed_info.duckdb')
            self.assertTrue(result)
            mock_download.assert_called_once_with(
                '/StockData/jp/listed_info.duckdb',
                '/local/listed_info.duckdb'
            )

    def test_upload_stocks_daily(self):
        """upload_stocks_daily便利メソッド"""
        with patch.object(self.client, 'upload_file', return_value=True) as mock_upload:
            result = self.client.upload_stocks_daily('1234', '/local/1234.duckdb')
            self.assertTrue(result)
            mock_upload.assert_called_once_with(
                '/local/1234.duckdb',
                '/StockData/jp/stocks_daily/1234.duckdb'
            )


if __name__ == '__main__':
    unittest.main()
