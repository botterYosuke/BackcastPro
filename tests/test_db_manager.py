import unittest
from unittest.mock import patch, MagicMock
import os
import shutil
import tempfile
import pandas as pd
import duckdb
import sys
from datetime import datetime

# Ensure src is in pythonpath
sys.path.insert(0, os.path.abspath("src"))

from BackcastPro.api.db_manager import db_manager


class TestDbManager(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for the cache
        self.test_dir = tempfile.mkdtemp()
        os.environ["STOCKDATA_CACHE_DIR"] = self.test_dir
        self.db_manager = db_manager()
        # Mock cloud download to prevent real HTTP requests during tests
        self._download_patcher = patch.object(
            db_manager, '_download_from_cloud', return_value=False
        )
        self._download_patcher.start()

    def tearDown(self):
        self._download_patcher.stop()
        # Remove the temporary directory after the test
        shutil.rmtree(self.test_dir)
        if "STOCKDATA_CACHE_DIR" in os.environ:
            del os.environ["STOCKDATA_CACHE_DIR"]

    def test_init_creates_cache_dir(self):
        """Test that the cache directory is created upon initialization."""
        self.assertTrue(os.path.exists(self.test_dir))
        self.assertTrue(self.db_manager.isEnable)

    def test_get_db_creates_directory_and_file(self):
        """Test that get_db creates the necessary directories and database file."""
        code = "1234"
        # Set _db_subdir to simulate subclass behavior or direct usage
        self.db_manager._db_subdir = "test_subdir"

        with self.db_manager.get_db(code) as db:
            pass

        db_path = os.path.join(self.test_dir, "test_subdir", f"{code}.duckdb")
        self.assertTrue(os.path.exists(db_path))

    @patch("BackcastPro.api.cloud_run_client.CloudRunClient")
    def test_get_db_downloads_from_cloud(self, MockCloudRunClient):
        """Test that get_db tries to download from cloud if local file is missing."""
        # Stop the setUp-level mock so the real _download_from_cloud runs
        self._download_patcher.stop()

        code = "5678"
        self.db_manager._db_subdir = "test_subdir"
        db_path = os.path.join(self.test_dir, "test_subdir", f"{code}.duckdb")

        # Mock client behavior
        mock_client_instance = MockCloudRunClient.return_value
        mock_client_instance.config.is_configured.return_value = True
        mock_client_instance.download_file.return_value = True

        # Ensure file doesn't exist initially
        if os.path.exists(db_path):
            os.remove(db_path)

        with self.db_manager.get_db(code) as db:
            pass

        # Verify download was attempted
        mock_client_instance.download_file.assert_called_once()

        # Re-start the setUp-level mock for tearDown
        self._download_patcher.start()

    def test_create_table_from_dataframe(self):
        """Test creating a table from a DataFrame."""
        code = "9999"
        self.db_manager._db_subdir = "test_subdir"

        df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"], "col3": [1.1, 2.2]})

        with self.db_manager.get_db(code) as db:
            self.db_manager._create_table_from_dataframe(
                db, "test_table", df, primary_keys=["col1"]
            )

            # Verify table exists
            result = db.execute("SELECT COUNT(*) FROM test_table").fetchone()
            self.assertEqual(result[0], 0)  # Table created but empty

            # Verify schema
            columns = db.execute("PRAGMA table_info(test_table)").fetchdf()
            col_names = columns["name"].tolist()
            self.assertIn("col1", col_names)
            self.assertIn("col2", col_names)
            self.assertIn("col3", col_names)
            self.assertIn("created_at", col_names)  # Metadata column

    def test_validate_table_schema(self):
        """Test schema validation."""
        code = "8888"
        self.db_manager._db_subdir = "test_subdir"

        df = pd.DataFrame({"col1": [1], "col2": ["a"]})

        with self.db_manager.get_db(code) as db:
            self.db_manager._create_table_from_dataframe(db, "test_table", df)

            # Case 1: Matching schema (should pass)
            self.db_manager._validate_table_schema(db, "test_table", df, "col1")

            # Case 2: Missing column in new data (should log warning but pass if key exists)
            df_missing = pd.DataFrame({"col1": [2]})  # col2 missing
            self.db_manager._validate_table_schema(db, "test_table", df_missing, "col1")

            # Case 3: Missing key column (should raise ValueError)
            df_no_key = pd.DataFrame({"col2": ["b"]})  # col1 (key) missing
            with self.assertRaises(ValueError):
                self.db_manager._validate_table_schema(
                    db, "test_table", df_no_key, "col1"
                )

    def test_batch_insert_data(self):
        """Test batch insertion."""
        code = "7777"
        self.db_manager._db_subdir = "test_subdir"

        # Create a df larger than default batch size (simulating small batch for test)
        df = pd.DataFrame({"id": range(10), "val": range(10)})

        with self.db_manager.get_db(code) as db:
            self.db_manager._create_table_from_dataframe(db, "test_table", df)

            # Insert with small batch size
            self.db_manager._batch_insert_data(db, "test_table", df, batch_size=3)

            count = db.execute("SELECT COUNT(*) FROM test_table").fetchone()[0]
            self.assertEqual(count, 10)

    def test_add_db_deduplication(self):
        """Test that __add_db__ deduplicates based on key."""
        code = "6666"
        self.db_manager._db_subdir = "test_subdir"

        # Initial data
        df1 = pd.DataFrame({"id": [1, 2], "val": ["a", "b"]})

        with self.db_manager.get_db(code) as db:
            self.db_manager.__create_db__(db, "test_table", df1, "id")

            # Add intersecting data
            df2 = pd.DataFrame({"id": [2, 3], "val": ["b_new", "c"]})
            self.db_manager.__add_db__(db, "test_table", df2, "id")

            # Check results
            result = db.execute("SELECT * FROM test_table ORDER BY id").fetchdf()
            self.assertEqual(len(result), 3)
            # id=2 should presumably NOT be updated if logic waits for unique new keys
            # logic in __add_db__: unique_disclosure_numbers = new - existing
            # so id=2 is in existing, so it is skipped.
            self.assertEqual(result.loc[result["id"] == 2, "val"].iloc[0], "b")
            self.assertEqual(result.loc[result["id"] == 3, "val"].iloc[0], "c")


if __name__ == "__main__":
    unittest.main()
