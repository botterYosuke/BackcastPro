"""tests for cloud-run/main.py (NAS FTPS Proxy version)"""
import ftplib
import io
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# cloud-run/ はパッケージ外なので sys.path に追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'cloud-run')))

from main import app, ALLOWED_PATHS, NASFtpsProxy


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Flask テストクライアント"""
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c
    # シングルトンをリセット
    if hasattr(app, '_nas_proxy'):
        delattr(app, '_nas_proxy')


@pytest.fixture
def mock_proxy():
    """NASFtpsProxy のモックを生成し _get_proxy を差し替える"""
    proxy = MagicMock(spec=NASFtpsProxy)
    with patch('main._get_proxy', return_value=proxy):
        yield proxy


# ===========================================================================
# TestAllowedPaths
# ===========================================================================

class TestAllowedPaths:
    """パスホワイトリスト正規表現"""

    def test_stocks_daily_valid(self):
        assert ALLOWED_PATHS.match('stocks_daily/1234.duckdb')

    def test_stocks_daily_5digit(self):
        assert ALLOWED_PATHS.match('stocks_daily/12345.duckdb')

    def test_stocks_board_valid(self):
        assert ALLOWED_PATHS.match('stocks_board/1234.duckdb')

    def test_listed_info_valid(self):
        assert ALLOWED_PATHS.match('listed_info.duckdb')

    def test_path_traversal_rejected(self):
        assert not ALLOWED_PATHS.match('../etc/passwd')

    def test_arbitrary_extension_rejected(self):
        assert not ALLOWED_PATHS.match('stocks_daily/1234.txt')

    def test_arbitrary_folder_rejected(self):
        assert not ALLOWED_PATHS.match('other_folder/1234.duckdb')

    def test_nested_path_rejected(self):
        assert not ALLOWED_PATHS.match('stocks_daily/sub/1234.duckdb')

    def test_empty_string_rejected(self):
        assert not ALLOWED_PATHS.match('')

    def test_non_numeric_code_rejected(self):
        assert not ALLOWED_PATHS.match('stocks_daily/abcd.duckdb')

    def test_no_code_rejected(self):
        assert not ALLOWED_PATHS.match('stocks_daily/.duckdb')


# ===========================================================================
# TestNASFtpsProxy
# ===========================================================================

class TestNASFtpsProxy:
    """NASFtpsProxy クラス"""

    def test_init(self):
        proxy = NASFtpsProxy(
            host='nas.example.com',
            port=21,
            username='user',
            password='pass',
            base_path='/StockData',
        )
        assert proxy.host == 'nas.example.com'
        assert proxy.port == 21
        assert proxy.username == 'user'
        assert proxy.password == 'pass'
        assert proxy.base_path == '/StockData'

    def test_base_path_trailing_slash_stripped(self):
        proxy = NASFtpsProxy(
            host='nas.example.com',
            port=21,
            username='user',
            password='pass',
            base_path='/StockData/',
        )
        assert proxy.base_path == '/StockData'

    def test_resolve_path(self):
        proxy = NASFtpsProxy(
            host='nas.example.com',
            port=21,
            username='user',
            password='pass',
            base_path='/StockData',
        )
        assert proxy._resolve_path('stocks_daily/1234.duckdb') == '/StockData/jp/stocks_daily/1234.duckdb'

    def test_resolve_path_listed_info(self):
        proxy = NASFtpsProxy(
            host='nas.example.com',
            port=21,
            username='user',
            password='pass',
            base_path='/StockData',
        )
        assert proxy._resolve_path('listed_info.duckdb') == '/StockData/jp/listed_info.duckdb'


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

    def test_valid_path_success(self, client, mock_proxy):
        from flask import Response
        mock_proxy.stream_file.return_value = Response(
            b'file_data', content_type='application/octet-stream'
        )
        resp = client.get('/jp/stocks_daily/1234.duckdb')
        assert resp.status_code == 200
        mock_proxy.stream_file.assert_called_once_with('stocks_daily/1234.duckdb')

    def test_invalid_path_returns_404(self, client):
        resp = client.get('/jp/malicious/path.exe')
        assert resp.status_code == 404

    def test_path_traversal_returns_404(self, client):
        resp = client.get('/jp/../etc/passwd')
        assert resp.status_code == 404

    def test_file_not_found_on_nas(self, client, mock_proxy):
        mock_proxy.stream_file.side_effect = ftplib.error_perm('550 File not found')
        resp = client.get('/jp/stocks_daily/1234.duckdb')
        assert resp.status_code == 404

    def test_listed_info(self, client, mock_proxy):
        from flask import Response
        mock_proxy.stream_file.return_value = Response(
            b'data', content_type='application/octet-stream'
        )
        resp = client.get('/jp/listed_info.duckdb')
        assert resp.status_code == 200
        mock_proxy.stream_file.assert_called_once_with('listed_info.duckdb')

    def test_stocks_board_valid(self, client, mock_proxy):
        from flask import Response
        mock_proxy.stream_file.return_value = Response(
            b'data', content_type='application/octet-stream'
        )
        resp = client.get('/jp/stocks_board/8306.duckdb')
        assert resp.status_code == 200
        mock_proxy.stream_file.assert_called_once_with('stocks_board/8306.duckdb')


# ===========================================================================
# TestUploadRoute
# ===========================================================================

class TestUploadRoute:
    """POST /jp/<path>"""

    def test_upload_success(self, client, mock_proxy):
        mock_proxy.upload_file.return_value = {
            'path': '/StockData/jp/stocks_daily/1234.duckdb',
            'size': 11,
        }

        with patch.dict(os.environ, {'UPLOAD_API_KEY': 'secret'}):
            resp = client.post(
                '/jp/stocks_daily/1234.duckdb',
                data=b'duckdb_data',
                headers={'X-API-Key': 'secret'},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['path'] == '/StockData/jp/stocks_daily/1234.duckdb'
        assert data['size'] == 11

    def test_missing_api_key_returns_401(self, client):
        with patch.dict(os.environ, {'UPLOAD_API_KEY': 'secret'}):
            resp = client.post('/jp/stocks_daily/1234.duckdb', data=b'data')
        assert resp.status_code == 401

    def test_wrong_api_key_returns_401(self, client):
        with patch.dict(os.environ, {'UPLOAD_API_KEY': 'secret'}):
            resp = client.post(
                '/jp/stocks_daily/1234.duckdb',
                data=b'data',
                headers={'X-API-Key': 'wrong'},
            )
        assert resp.status_code == 401

    def test_no_env_key_returns_401(self, client):
        env = os.environ.copy()
        env.pop('UPLOAD_API_KEY', None)
        with patch.dict(os.environ, env, clear=True):
            resp = client.post(
                '/jp/stocks_daily/1234.duckdb',
                data=b'data',
                headers={'X-API-Key': 'anything'},
            )
        assert resp.status_code == 401

    def test_invalid_path_returns_404(self, client):
        with patch.dict(os.environ, {'UPLOAD_API_KEY': 'secret'}):
            resp = client.post(
                '/jp/evil/path.exe',
                data=b'data',
                headers={'X-API-Key': 'secret'},
            )
        assert resp.status_code == 404

    def test_upload_sends_correct_data(self, client, mock_proxy):
        mock_proxy.upload_file.return_value = {'path': '/p', 'size': 17}

        with patch.dict(os.environ, {'UPLOAD_API_KEY': 'secret'}):
            client.post(
                '/jp/stocks_daily/1234.duckdb',
                data=b'my_duckdb_content',
                headers={'X-API-Key': 'secret'},
            )
        mock_proxy.upload_file.assert_called_once_with(
            'stocks_daily/1234.duckdb', b'my_duckdb_content'
        )


# ===========================================================================
# TestErrorHandlers
# ===========================================================================

class TestErrorHandlers:
    """Flask エラーハンドラ"""

    def test_ftp_error_perm(self, client, mock_proxy):
        mock_proxy.stream_file.side_effect = ftplib.error_perm('550 Not found')
        resp = client.get('/jp/stocks_daily/1234.duckdb')
        assert resp.status_code == 404

    def test_ftp_error_temp(self, client, mock_proxy):
        mock_proxy.stream_file.side_effect = ftplib.error_temp('421 Service not available')
        resp = client.get('/jp/stocks_daily/1234.duckdb')
        assert resp.status_code == 503

    def test_unexpected_exception(self, client, mock_proxy):
        mock_proxy.stream_file.side_effect = RuntimeError("boom")
        resp = client.get('/jp/stocks_daily/1234.duckdb')
        assert resp.status_code == 500
        assert b'Internal error' in resp.data
