import unittest
from unittest.mock import patch, MagicMock
import os
import shutil
import sys

# Ensure src is in pythonpath
sys.path.insert(0, os.path.abspath('src'))

from BackcastPro.api.db_stocks_info import db_stocks_info

class TestDbStocksInfo(unittest.TestCase):
    def setUp(self):
        # Set cache dir to a temp path to avoid cluttering unrelated dirs
        self.test_cache_dir = os.path.abspath("test_cache_db_stocks_info")
        os.environ['BACKCASTPRO_CACHE_DIR'] = self.test_cache_dir
        
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
        if 'BACKCASTPRO_CACHE_DIR' in os.environ:
            del os.environ['BACKCASTPRO_CACHE_DIR']

    def test_download_from_ftp_success(self):
        """Test successful download from FTP"""
        # Ensure ftplib is imported so patch works correctly if lazy loaded
        import ftplib
        
        with patch('ftplib.FTP') as mock_ftp_cls:
            mock_ftp = mock_ftp_cls.return_value
            # Context manager return value must be set to the mock instance
            mock_ftp.__enter__.return_value = mock_ftp
            
            # Setup mock to simulate success
            mock_ftp.connect.return_value = None
            mock_ftp.login.return_value = None
            mock_ftp.voidcmd.return_value = "200 Type set to I"
            mock_ftp.size.return_value = 1024 
            
            # Mock retrbinary to write something to the file
            def side_effect_retrbinary(cmd, callback):
                callback(b'dummy content')
            mock_ftp.retrbinary.side_effect = side_effect_retrbinary

            # Use a temp path for the download target
            test_path = os.path.join(self.test_cache_dir, "test_downloaded.duckdb")
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(test_path), exist_ok=True)
            
            # Call the method
            code = "dummy_code" 
            result = self.db_info._download_from_ftp(code, test_path)
            
            # Assertions
            self.assertTrue(result, "Download should return True on success")
            mock_ftp.connect.assert_called()
            mock_ftp.login.assert_called()
            mock_ftp.retrbinary.assert_called()
            
            # Check file exists and content is correct
            self.assertTrue(os.path.exists(test_path), "Downloaded file should exist")
            with open(test_path, 'rb') as f:
                self.assertEqual(f.read(), b'dummy content')

    def test_download_from_ftp_failure_connection(self):
        """Test failure during FTP connection"""
        with patch('ftplib.FTP') as mock_ftp_cls:
            mock_ftp = mock_ftp_cls.return_value
            mock_ftp.__enter__.return_value = mock_ftp
            
            # Simulate connection error
            mock_ftp.connect.side_effect = Exception("Connection error")
            
            test_path = os.path.join(self.test_cache_dir, "test_fail.duckdb")
            
            result = self.db_info._download_from_ftp("dummy_code", test_path)
            
            self.assertFalse(result, "Download should return False on connection error")
            self.assertFalse(os.path.exists(test_path), "File should not exist")

    def test_download_from_ftp_file_not_found(self):
        """Test behavior when file is not found on server (size check fails)"""
        with patch('ftplib.FTP') as mock_ftp_cls:
            mock_ftp = mock_ftp_cls.return_value
            mock_ftp.__enter__.return_value = mock_ftp
            
            # Simulate file not found by raising exception on size/voidcmd check
            mock_ftp.voidcmd.side_effect = Exception("File not found check")
            
            test_path = os.path.join(self.test_cache_dir, "test_notfound.duckdb")
            
            result = self.db_info._download_from_ftp("dummy_code", test_path)
            
            self.assertFalse(result, "Download should return False if file not found on server")

if __name__ == '__main__':
    unittest.main()
