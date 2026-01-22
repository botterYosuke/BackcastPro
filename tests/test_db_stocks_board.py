import pytest
import pandas as pd
import os
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import sys

# テスト対象のモジュールをインポート
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from BackcastPro.api.db_stocks_board import db_stocks_board


@pytest.fixture
def temp_cache_dir():
    """テスト用の一時キャッシュディレクトリを作成"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # テスト終了後にクリーンアップ
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def db_board(temp_cache_dir):
    """テスト用のdb_stocks_boardインスタンスを作成"""
    with patch.dict(os.environ, {'BACKCASTPRO_CACHE_DIR': temp_cache_dir}):
        instance = db_stocks_board()
        instance.isEnable = True  # 強制的に有効化
        yield instance


@pytest.fixture
def sample_board_data():
    """サンプルの板情報データを作成"""
    timestamps = pd.date_range(start='2024-01-01 09:00:00', periods=10, freq='1min')
    data = {
        'Timestamp': timestamps,
        'BidPrice1': [100.0 + i for i in range(10)],
        'BidVolume1': [1000 + i * 10 for i in range(10)],
        'AskPrice1': [101.0 + i for i in range(10)],
        'AskVolume1': [900 + i * 10 for i in range(10)],
    }
    return pd.DataFrame(data)


class TestDbStocksBoard:
    """db_stocks_boardクラスのテスト"""

    def test_init(self, temp_cache_dir):
        """初期化のテスト"""
        with patch.dict(os.environ, {'BACKCASTPRO_CACHE_DIR': temp_cache_dir}):
            instance = db_stocks_board()
            assert instance.cache_dir == temp_cache_dir
            assert instance.isEnable is True

    def test_save_stock_board_basic(self, db_board, sample_board_data):
        """基本的な板情報の保存テスト"""
        code = "1234"

        # データを保存
        db_board.save_stock_board(code, sample_board_data)

        # データを読み込んで確認
        loaded_df = db_board.load_stock_board_from_cache(code)

        assert len(loaded_df) == len(sample_board_data)
        assert 'Code' in loaded_df.columns
        assert 'Timestamp' in loaded_df.columns
        assert all(loaded_df['Code'] == code)

    def test_save_stock_board_empty_dataframe(self, db_board):
        """空のDataFrameの保存テスト"""
        code = "1234"
        empty_df = pd.DataFrame()

        # 空のDataFrameは保存をスキップするべき
        db_board.save_stock_board(code, empty_df)

        # データが保存されていないことを確認
        loaded_df = db_board.load_stock_board_from_cache(code)
        assert loaded_df.empty

    def test_save_stock_board_without_timestamp(self, db_board):
        """Timestampカラムがない場合のテスト"""
        code = "1234"
        data = {
            'BidPrice1': [100.0, 101.0, 102.0],
            'BidVolume1': [1000, 1100, 1200],
        }
        df = pd.DataFrame(data)

        # Timestampがない場合、自動的に追加される
        # ただし、同じ時刻が全行に追加されるため、重複排除で1行だけが保存される
        db_board.save_stock_board(code, df)

        loaded_df = db_board.load_stock_board_from_cache(code)
        assert 'Timestamp' in loaded_df.columns
        # 同じTimestampのため、重複排除により1行だけが保存される
        assert len(loaded_df) >= 1

    def test_save_stock_board_with_timestamp_index(self, db_board):
        """Timestampがインデックスになっている場合のテスト"""
        code = "1234"
        timestamps = pd.date_range(start='2024-01-01 09:00:00', periods=5, freq='1min')
        data = {
            'BidPrice1': [100.0 + i for i in range(5)],
            'BidVolume1': [1000 + i * 10 for i in range(5)],
        }
        df = pd.DataFrame(data, index=timestamps)
        df.index.name = 'Timestamp'

        # インデックスからカラムに変換される
        db_board.save_stock_board(code, df)

        loaded_df = db_board.load_stock_board_from_cache(code)
        assert 'Timestamp' in loaded_df.columns
        # Timestampインデックスが正しくカラムに変換され、5行すべてが保存される
        assert len(loaded_df) == 5

    def test_save_stock_board_duplicate_data(self, db_board, sample_board_data):
        """重複データの処理テスト"""
        code = "1234"

        # 最初に保存
        db_board.save_stock_board(code, sample_board_data)
        loaded_df_1 = db_board.load_stock_board_from_cache(code)
        count_1 = len(loaded_df_1)

        # 同じデータを再度保存（重複）
        db_board.save_stock_board(code, sample_board_data)
        loaded_df_2 = db_board.load_stock_board_from_cache(code)
        count_2 = len(loaded_df_2)

        # 重複データは保存されないため、件数は変わらない
        assert count_1 == count_2

    def test_save_stock_board_append_new_data(self, db_board, sample_board_data):
        """新しいデータの追加テスト"""
        code = "1234"

        # 最初のデータを保存
        db_board.save_stock_board(code, sample_board_data)
        count_1 = len(db_board.load_stock_board_from_cache(code))

        # 新しいタイムスタンプのデータを作成
        new_timestamps = pd.date_range(start='2024-01-01 09:20:00', periods=5, freq='1min')
        new_data = {
            'Timestamp': new_timestamps,
            'BidPrice1': [110.0 + i for i in range(5)],
            'BidVolume1': [1100 + i * 10 for i in range(5)],
            'AskPrice1': [111.0 + i for i in range(5)],
            'AskVolume1': [1000 + i * 10 for i in range(5)],
        }
        new_df = pd.DataFrame(new_data)

        # 新しいデータを追加
        db_board.save_stock_board(code, new_df)
        count_2 = len(db_board.load_stock_board_from_cache(code))

        # データが追加されたことを確認
        assert count_2 == count_1 + len(new_df)

    def test_load_stock_board_with_date_range(self, db_board, sample_board_data):
        """日付範囲指定での読み込みテスト"""
        code = "1234"

        # データを保存
        db_board.save_stock_board(code, sample_board_data)

        # 日付範囲を指定して読み込み
        from_dt = datetime(2024, 1, 1, 9, 3, 0)
        to_dt = datetime(2024, 1, 1, 9, 6, 0)

        loaded_df = db_board.load_stock_board_from_cache(code, from_=from_dt, to=to_dt)

        # 指定範囲内のデータのみが取得されることを確認
        assert len(loaded_df) > 0
        assert len(loaded_df) < len(sample_board_data)

        # タイムスタンプが範囲内であることを確認
        loaded_df['Timestamp'] = pd.to_datetime(loaded_df['Timestamp'])
        assert all(loaded_df['Timestamp'] >= from_dt)
        assert all(loaded_df['Timestamp'] <= to_dt)

    def test_load_stock_board_nonexistent_code(self, db_board):
        """存在しない銘柄コードの読み込みテスト"""
        code = "9999"

        # 存在しないコードの場合は空のDataFrameが返される
        loaded_df = db_board.load_stock_board_from_cache(code)
        assert loaded_df.empty

    def test_metadata_save_and_load(self, db_board, sample_board_data):
        """メタデータの保存と読み込みテスト"""
        code = "1234"

        # データを保存（メタデータも自動的に保存される）
        db_board.save_stock_board(code, sample_board_data)

        # メタデータを取得
        with db_board.get_db(code) as db:
            metadata = db_board._get_metadata(db, code)

        assert metadata is not None
        assert metadata['code'] == code
        assert metadata['from_timestamp'] is not None
        assert metadata['to_timestamp'] is not None
        assert metadata['record_count'] == len(sample_board_data)

    def test_metadata_update_on_append(self, db_board, sample_board_data):
        """データ追加時のメタデータ更新テスト"""
        code = "1234"

        # 最初のデータを保存
        db_board.save_stock_board(code, sample_board_data)

        with db_board.get_db(code) as db:
            metadata_1 = db_board._get_metadata(db, code)

        # 新しいデータを追加（より古い時刻）
        old_timestamps = pd.date_range(start='2024-01-01 08:00:00', periods=5, freq='1min')
        old_data = {
            'Timestamp': old_timestamps,
            'BidPrice1': [90.0 + i for i in range(5)],
            'BidVolume1': [900 + i * 10 for i in range(5)],
            'AskPrice1': [91.0 + i for i in range(5)],
            'AskVolume1': [800 + i * 10 for i in range(5)],
        }
        old_df = pd.DataFrame(old_data)

        db_board.save_stock_board(code, old_df)

        with db_board.get_db(code) as db:
            metadata_2 = db_board._get_metadata(db, code)

        # from_timestampが更新されたことを確認
        assert metadata_2['from_timestamp'] < metadata_1['from_timestamp']
        assert metadata_2['record_count'] > metadata_1['record_count']

    def test_get_db_context_manager(self, db_board):
        """get_dbコンテキストマネージャーのテスト"""
        code = "1234"

        # コンテキストマネージャーでDBを取得
        with db_board.get_db(code) as db:
            assert db is not None
            # 簡単なクエリを実行
            result = db.execute("SELECT 1 as test").fetchone()
            assert result[0] == 1

    def test_get_db_creates_directory(self, db_board):
        """get_dbがディレクトリを作成することを確認"""
        code = "5678"

        # DBファイルのパスを確認
        db_path = os.path.join(db_board.cache_dir, "stocks_board", f"{code}.duckdb")
        assert not os.path.exists(db_path)

        # DBを取得
        with db_board.get_db(code) as db:
            assert db is not None

        # DBファイルが作成されたことを確認
        assert os.path.exists(db_path)

    def test_save_invalid_timestamp(self, db_board):
        """無効なTimestampの処理テスト"""
        code = "1234"

        # 無効なTimestampを含むデータ
        data = {
            'Timestamp': ['2024-01-01 09:00:00', 'invalid', '2024-01-01 09:02:00'],
            'BidPrice1': [100.0, 101.0, 102.0],
            'BidVolume1': [1000, 1100, 1200],
        }
        df = pd.DataFrame(data)

        # 無効な行は除外される
        db_board.save_stock_board(code, df)

        loaded_df = db_board.load_stock_board_from_cache(code)
        # 無効な1行が除外され、2行だけ保存される
        assert len(loaded_df) == 2

    def test_is_enable_false(self, temp_cache_dir):
        """isEnableがFalseの場合のテスト"""
        with patch.dict(os.environ, {'BACKCASTPRO_CACHE_DIR': temp_cache_dir}):
            instance = db_stocks_board()
            instance.isEnable = False

            # isEnable=Falseの場合、保存も読み込みも何もしない
            data = {
                'Timestamp': ['2024-01-01 09:00:00'],
                'BidPrice1': [100.0],
            }
            df = pd.DataFrame(data)

            instance.save_stock_board("1234", df)
            loaded_df = instance.load_stock_board_from_cache("1234")

            assert loaded_df.empty

    def test_ensure_metadata_table(self, db_board):
        """メタデータテーブルの作成テスト"""
        code = "1234"

        with db_board.get_db(code) as db:
            # メタデータテーブルを確認
            db_board._ensure_metadata_table(db)

            # テーブルが存在することを確認
            assert db_board._table_exists(db, "stocks_board_metadata")

    def test_code_with_suffix_fallback(self, db_board, sample_board_data):
        """銘柄コードのサフィックス対応テスト（例: 1234T → 1234）"""
        code_with_suffix = "1234T"

        # サフィックス付きコードでデータを保存
        # get_dbのフォールバック機能により、1234.duckdbが作成される
        db_board.save_stock_board(code_with_suffix, sample_board_data)

        # サフィックス付きコードで読み込み
        loaded_df = db_board.load_stock_board_from_cache(code_with_suffix)

        # フォールバック機能により、1234のDBファイルが参照される
        assert len(loaded_df) == len(sample_board_data)

    def test_load_with_string_datetime(self, db_board, sample_board_data):
        """文字列形式のdatetimeでの読み込みテスト"""
        code = "1234"

        # データを保存
        db_board.save_stock_board(code, sample_board_data)

        # 文字列形式で日付範囲を指定
        from_str = "2024-01-01 09:03:00"
        to_str = "2024-01-01 09:06:00"

        loaded_df = db_board.load_stock_board_from_cache(code, from_=from_str, to=to_str)

        # データが正しく読み込まれることを確認
        assert len(loaded_df) > 0

    def test_concurrent_save_same_code(self, db_board, sample_board_data):
        """同じ銘柄コードへの連続保存テスト（トランザクション確認）"""
        code = "1234"

        # 連続して保存
        db_board.save_stock_board(code, sample_board_data.iloc[:5])
        db_board.save_stock_board(code, sample_board_data.iloc[5:])

        # 全データが保存されていることを確認
        loaded_df = db_board.load_stock_board_from_cache(code)
        assert len(loaded_df) == len(sample_board_data)
