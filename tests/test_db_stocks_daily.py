import unittest
from unittest.mock import patch, MagicMock
import os
import shutil
import sys
import pandas as pd
from datetime import datetime
import duckdb

# Ensure src is in pythonpath
sys.path.insert(0, os.path.abspath('src'))

from BackcastPro.api.db_stocks_daily import db_stocks_daily

class TestDbStocksDaily(unittest.TestCase):
    def setUp(self):
        # Set cache dir to a temp path
        self.test_cache_dir = os.path.abspath("test_cache_db_stocks_daily")
        os.environ['BACKCASTPRO_CACHE_DIR'] = self.test_cache_dir
        
        # Initialize the class under test
        self.db_daily = db_stocks_daily()
        # Mock isEnable to True forcefully in case dir creation failed silently (though it shouldn't)
        self.db_daily.isEnable = True

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
        # Ensure ftplib is imported so patch works
        import ftplib
        
        with patch('ftplib.FTP') as mock_ftp_cls:
            mock_ftp = mock_ftp_cls.return_value
            mock_ftp.__enter__.return_value = mock_ftp
            
            mock_ftp.connect.return_value = None
            mock_ftp.login.return_value = None
            mock_ftp.voidcmd.return_value = "200 Type set to I"
            mock_ftp.size.return_value = 1024 
            
            def side_effect_retrbinary(cmd, callback):
                callback(b'dummy content')
            mock_ftp.retrbinary.side_effect = side_effect_retrbinary

            code = "9999"
            test_path = os.path.join(self.test_cache_dir, "stocks", f"{code}.duckdb")
            os.makedirs(os.path.dirname(test_path), exist_ok=True)
            
            result = self.db_daily._download_from_ftp(code, test_path)
            
            self.assertTrue(result)
            self.assertTrue(os.path.exists(test_path))

    def test_metadata_operations(self):
        """Test _save_metadata and _get_metadata"""
        code = "1111"
        # We need a DB connection. Since get_db is a context manager using the cache dir, 
        # let's manually create a db file and connect to avoid FTP logic triggering in get_db
        db_path = os.path.join(self.test_cache_dir, "stocks", f"{code}.duckdb")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        con = duckdb.connect(db_path)
        try:
            # 1. Test saving new metadata
            self.db_daily._save_metadata(con, code, "2024-01-01", "2024-01-10", 10)
            
            meta = self.db_daily._get_metadata(con, code)
            self.assertIsNotNone(meta)
            self.assertEqual(meta['code'], code)
            self.assertEqual(str(meta['from_date']), "2024-01-01")
            self.assertEqual(str(meta['to_date']), "2024-01-10")
            self.assertEqual(meta['record_count'], 10)

            # 2. Test updating metadata (extending period)
            self.db_daily._save_metadata(con, code, "2024-01-11", "2024-01-20", 20)
            meta = self.db_daily._get_metadata(con, code)
            self.assertEqual(str(meta['from_date']), "2024-01-01") # Should keep oldest
            self.assertEqual(str(meta['to_date']), "2024-01-20")   # Should update to newest
            self.assertEqual(meta['record_count'], 20)             # Should update count
            
        finally:
            con.close()

    def test_check_period_coverage(self):
        """Unit test for period coverage logic"""
        metadata = {
            'from_date': datetime(2024, 1, 1).date(),
            'to_date': datetime(2024, 1, 31).date()
        }
        
        # Case 1: Fully covered
        res = self.db_daily._check_period_coverage(metadata, datetime(2024, 1, 5), datetime(2024, 1, 10))
        self.assertTrue(res['is_covered'])
        
        # Case 2: Partially covered (start before)
        res = self.db_daily._check_period_coverage(metadata, datetime(2023, 12, 31), datetime(2024, 1, 10))
        self.assertFalse(res['is_covered'])
        
        # Case 3: Partially covered (end after)
        res = self.db_daily._check_period_coverage(metadata, datetime(2024, 1, 20), datetime(2024, 2, 1))
        self.assertFalse(res['is_covered'])
        
        # Case 4: Not covered (disjoint)
        res = self.db_daily._check_period_coverage(metadata, datetime(2024, 2, 1), datetime(2024, 2, 10))
        self.assertFalse(res['is_covered'])

        # Case 5: No requirements (None) -> treated as "get all available", so covered if metadata exists
        res = self.db_daily._check_period_coverage(metadata, None, None)
        self.assertTrue(res['is_covered'])

    def test_save_and_load_stock_prices(self):
        """Test full save and load cycle"""
        code = "2222"
        
        # Prepare dummy data
        data = {
            'Date': [datetime(2024,1,1), datetime(2024,1,2)],
            'Open': [100, 101],
            'High': [110, 111],
            'Low': [90, 91],
            'Close': [105, 106],
            'Volume': [1000, 1100]
        }
        df = pd.DataFrame(data)
        
        # 1. Save data
        # Mocking _download_from_ftp to avoid FTP check when get_db calls it on missing file
        with patch.object(self.db_daily, '_download_from_ftp', return_value=False):
            self.db_daily.save_stock_prices(code, df)
        
        # 2. Check DB content manually
        db_path = os.path.join(self.test_cache_dir, "stocks", f"{code}.duckdb")
        self.assertTrue(os.path.exists(db_path))
        
        con = duckdb.connect(db_path)
        try:
            # Check data table
            count = con.execute("SELECT COUNT(*) FROM stocks_daily").fetchone()[0]
            self.assertEqual(count, 2)
            
            # Check metadata table
            meta_count = con.execute("SELECT record_count FROM stocks_daily_metadata WHERE \"Code\"=?", [code]).fetchone()[0]
            self.assertEqual(meta_count, 2)
            
            # Check date range in metadata
            dates = con.execute("SELECT from_date, to_date FROM stocks_daily_metadata WHERE \"Code\"=?", [code]).fetchone()
            self.assertEqual(str(dates[0]), "2024-01-01")
            self.assertEqual(str(dates[1]), "2024-01-02")
        finally:
            con.close()
            
        # 3. Load data via load_stock_prices_from_cache
        loaded_df = self.db_daily.load_stock_prices_from_cache(code)
        self.assertFalse(loaded_df.empty)
        self.assertEqual(len(loaded_df), 2)
        
        # 4. Load with date filtering
        loaded_df_filtered = self.db_daily.load_stock_prices_from_cache(
            code, from_=datetime(2024,1,2), to=datetime(2024,1,2)
        )
        self.assertEqual(len(loaded_df_filtered), 1)
        # 2024-01-02 should be the only one
        self.assertEqual(pd.to_datetime(loaded_df_filtered['Date'].iloc[0]), datetime(2024,1,2))
        
    def test_duplicates_handling(self):
        """Test that duplicates are not inserted"""
        code = "3333"
        data = {
            'Date': [datetime(2024,1,1)],
            'Open': [100], 'High': [110], 'Low': [90], 'Close': [105], 'Volume': [1000]
        }
        df = pd.DataFrame(data)
        
        with patch.object(self.db_daily, '_download_from_ftp', return_value=False):
            # First save
            self.db_daily.save_stock_prices(code, df)
            
            # Second save (same data)
            self.db_daily.save_stock_prices(code, df)
            
        con = duckdb.connect(os.path.join(self.test_cache_dir, "stocks", f"{code}.duckdb"))
        try:
            count = con.execute("SELECT COUNT(*) FROM stocks_daily").fetchone()[0]
            # Should still be 1
            self.assertEqual(count, 1)
        finally:
            con.close()

if __name__ == '__main__':
    unittest.main()
