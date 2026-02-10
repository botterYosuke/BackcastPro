"""tests for cloud-run/main.py (local file server version)"""
import os
import sys
from pathlib import Path

import pytest

# cloud-run/ はパッケージ外なので sys.path に追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'cloud-run')))

from main import app, ALLOWED_PATHS


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def data_dir(tmp_path):
    """テスト用データディレクトリを作成"""
    jp = tmp_path / "jp"
    (jp / "stocks_daily").mkdir(parents=True)
    (jp / "stocks_board").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def client(data_dir, monkeypatch):
    """Flask テストクライアント（DATA_DIR をテスト用に差し替え）"""
    monkeypatch.setattr('main.DATA_DIR', str(data_dir))
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ===========================================================================
# TestAllowedPaths
# ===========================================================================

class TestAllowedPaths:
    """パスホワイトリスト正規表現"""

    def test_stocks_daily_valid(self):
        assert ALLOWED_PATHS.match('jp/stocks_daily/1234.duckdb')

    def test_stocks_daily_5digit(self):
        assert ALLOWED_PATHS.match('jp/stocks_daily/12345.duckdb')

    def test_stocks_board_valid(self):
        assert ALLOWED_PATHS.match('jp/stocks_board/1234.duckdb')

    def test_listed_info_valid(self):
        assert ALLOWED_PATHS.match('jp/listed_info.duckdb')

    def test_path_traversal_rejected(self):
        assert not ALLOWED_PATHS.match('../etc/passwd')

    def test_arbitrary_extension_rejected(self):
        assert not ALLOWED_PATHS.match('jp/stocks_daily/1234.txt')

    def test_arbitrary_folder_rejected(self):
        assert not ALLOWED_PATHS.match('jp/other_folder/1234.duckdb')

    def test_nested_path_rejected(self):
        assert not ALLOWED_PATHS.match('jp/stocks_daily/sub/1234.duckdb')

    def test_empty_string_rejected(self):
        assert not ALLOWED_PATHS.match('')

    def test_non_numeric_code_rejected(self):
        assert not ALLOWED_PATHS.match('jp/stocks_daily/abcd.duckdb')

    def test_no_code_rejected(self):
        assert not ALLOWED_PATHS.match('jp/stocks_daily/.duckdb')

    def test_without_jp_prefix_rejected(self):
        assert not ALLOWED_PATHS.match('stocks_daily/1234.duckdb')


# ===========================================================================
# TestHealthRoute
# ===========================================================================

class TestHealthRoute:
    """GET /"""

    def test_returns_ok(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        assert resp.data == b'OK'


# ===========================================================================
# TestDownloadRoute
# ===========================================================================

class TestDownloadRoute:
    """GET /jp/<path>"""

    def test_valid_path_success(self, client, data_dir):
        # テスト用ファイルを配置
        file_path = data_dir / "jp" / "stocks_daily" / "1234.duckdb"
        file_path.write_bytes(b'duckdb_data')

        resp = client.get('/jp/stocks_daily/1234.duckdb')
        assert resp.status_code == 200
        assert resp.data == b'duckdb_data'

    def test_invalid_path_returns_404(self, client):
        resp = client.get('/jp/malicious/path.exe')
        assert resp.status_code == 404

    def test_path_traversal_returns_404(self, client):
        resp = client.get('/jp/../etc/passwd')
        assert resp.status_code == 404

    def test_file_not_found(self, client):
        resp = client.get('/jp/stocks_daily/1234.duckdb')
        assert resp.status_code == 404

    def test_listed_info(self, client, data_dir):
        file_path = data_dir / "jp" / "listed_info.duckdb"
        file_path.write_bytes(b'listed_data')

        resp = client.get('/jp/listed_info.duckdb')
        assert resp.status_code == 200
        assert resp.data == b'listed_data'

    def test_stocks_board_valid(self, client, data_dir):
        file_path = data_dir / "jp" / "stocks_board" / "8306.duckdb"
        file_path.write_bytes(b'board_data')

        resp = client.get('/jp/stocks_board/8306.duckdb')
        assert resp.status_code == 200
        assert resp.data == b'board_data'


# ===========================================================================
# TestErrorHandlers
# ===========================================================================

class TestErrorHandlers:
    """Flask エラーハンドラ"""

    def test_unexpected_exception(self, client):
        # download_file 内で予期しない例外が起きた場合
        from unittest.mock import patch
        with patch('main.send_from_directory', side_effect=RuntimeError("boom")):
            resp = client.get('/jp/stocks_daily/1234.duckdb')
        assert resp.status_code == 500
        assert b'Internal error' in resp.data
