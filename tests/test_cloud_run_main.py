"""tests for cloud-run/main.py"""
import io
import json
import os
import sys
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

# cloud-run/ はパッケージ外なので sys.path に追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'cloud-run')))

# main.py のインポート時に google api を使うため、インポート前にモック不要
# （トップレベルではインスタンス化しないため）
import main as cloud_main
from main import app, ALLOWED_PATHS, GoogleDriveProxy


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
    if hasattr(app, '_drive_proxy'):
        delattr(app, '_drive_proxy')


@pytest.fixture
def mock_proxy():
    """GoogleDriveProxy のモックを生成し _get_proxy を差し替える"""
    proxy = MagicMock(spec=GoogleDriveProxy)
    proxy.root_folder_id = 'root123'
    proxy._folder_cache = {}
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
# TestGoogleDriveProxy
# ===========================================================================

class TestGoogleDriveProxy:
    """GoogleDriveProxy クラス"""

    def _make_proxy(self):
        """モック済み Drive サービスで GoogleDriveProxy を生成"""
        mock_creds = MagicMock()
        with patch('main.build') as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            proxy = GoogleDriveProxy(mock_creds, 'root_folder_id')
        return proxy, mock_service

    def test_init(self):
        proxy, mock_service = self._make_proxy()
        assert proxy.root_folder_id == 'root_folder_id'
        assert proxy._folder_cache == {}
        assert proxy.service is mock_service

    def test_find_subfolder_success(self):
        proxy, svc = self._make_proxy()
        svc.files().list().execute.return_value = {
            'files': [{'id': 'folder_abc', 'name': 'stocks_daily'}]
        }
        result = proxy.find_subfolder('stocks_daily')
        assert result == 'folder_abc'

    def test_find_subfolder_not_found(self):
        proxy, svc = self._make_proxy()
        svc.files().list().execute.return_value = {'files': []}
        result = proxy.find_subfolder('nonexistent')
        assert result is None

    def test_find_subfolder_caching(self):
        proxy, svc = self._make_proxy()
        svc.files().list().execute.return_value = {
            'files': [{'id': 'folder_abc', 'name': 'stocks_daily'}]
        }
        result1 = proxy.find_subfolder('stocks_daily')
        # execute の呼び出し回数をリセット
        svc.files().list().execute.reset_mock()
        result2 = proxy.find_subfolder('stocks_daily')
        # 2回目はキャッシュから返されるので execute は呼ばれない
        svc.files().list().execute.assert_not_called()
        assert result1 == result2 == 'folder_abc'

    def test_find_file_success(self):
        proxy, svc = self._make_proxy()
        svc.files().list().execute.return_value = {
            'files': [{'id': 'file_123', 'name': '1234.duckdb'}]
        }
        result = proxy.find_file('folder_abc', '1234.duckdb')
        assert result == 'file_123'

    def test_find_file_not_found(self):
        proxy, svc = self._make_proxy()
        svc.files().list().execute.return_value = {'files': []}
        result = proxy.find_file('folder_abc', '9999.duckdb')
        assert result is None

    def test_upload_file_new(self):
        proxy, svc = self._make_proxy()
        # find_file は None を返す（新規ファイル）
        svc.files().list().execute.return_value = {'files': []}
        svc.files().create().execute.return_value = {'id': 'new_id'}

        result = proxy.upload_file('folder_abc', 'test.duckdb', b'data')
        assert result == 'new_id'

    def test_upload_file_update(self):
        proxy, svc = self._make_proxy()
        # find_file は既存IDを返す
        svc.files().list().execute.return_value = {
            'files': [{'id': 'existing_id', 'name': 'test.duckdb'}]
        }
        svc.files().update().execute.return_value = {'id': 'existing_id'}

        result = proxy.upload_file('folder_abc', 'test.duckdb', b'data')
        assert result == 'existing_id'


# ===========================================================================
# TestBuildCredentials
# ===========================================================================

class TestBuildCredentials:
    """認証情報構築"""

    @patch('main.service_account.Credentials.from_service_account_info')
    def test_from_env_var(self, mock_from_sa):
        sa_json = json.dumps({'type': 'service_account', 'project_id': 'test'})
        with patch.dict(os.environ, {'GOOGLE_SERVICE_ACCOUNT_JSON': sa_json}):
            cloud_main._build_credentials()
        mock_from_sa.assert_called_once()
        call_args = mock_from_sa.call_args
        assert call_args[0][0]['type'] == 'service_account'

    @patch('google.auth.default', return_value=(MagicMock(), 'project'))
    def test_fallback_to_default(self, mock_default):
        env = os.environ.copy()
        env.pop('GOOGLE_SERVICE_ACCOUNT_JSON', None)
        with patch.dict(os.environ, env, clear=True):
            cloud_main._build_credentials()
        mock_default.assert_called_once()


# ===========================================================================
# TestGetProxy
# ===========================================================================

class TestGetProxy:
    """シングルトン生成"""

    def teardown_method(self):
        if hasattr(app, '_drive_proxy'):
            delattr(app, '_drive_proxy')

    @patch('main.build')
    @patch('main._build_credentials')
    def test_creates_singleton(self, mock_creds, mock_build):
        with patch.dict(os.environ, {'GOOGLE_DRIVE_ROOT_FOLDER_ID': 'root123'}):
            mock_build.return_value = MagicMock()
            p1 = cloud_main._get_proxy()
            p2 = cloud_main._get_proxy()
        assert p1 is p2

    @patch('main.build')
    @patch('main._build_credentials')
    def test_subfolder_resolution(self, mock_creds, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.files().list().execute.return_value = {
            'files': [{'id': 'resolved_id', 'name': 'jp'}]
        }
        with patch.dict(os.environ, {'GOOGLE_DRIVE_ROOT_FOLDER_ID': 'root123'}):
            proxy = cloud_main._get_proxy('jp')
        assert proxy.root_folder_id == 'resolved_id'


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
        mock_proxy.find_subfolder.return_value = 'folder_abc'
        mock_proxy.find_file.return_value = 'file_123'
        from flask import Response
        mock_proxy.stream_file.return_value = Response(
            b'file_data', content_type='application/octet-stream'
        )
        resp = client.get('/jp/stocks_daily/1234.duckdb')
        assert resp.status_code == 200

    def test_invalid_path_returns_404(self, client):
        resp = client.get('/jp/malicious/path.exe')
        assert resp.status_code == 404

    def test_path_traversal_returns_404(self, client):
        resp = client.get('/jp/../etc/passwd')
        assert resp.status_code == 404

    def test_subfolder_not_found(self, client, mock_proxy):
        mock_proxy.find_subfolder.return_value = None
        resp = client.get('/jp/stocks_daily/1234.duckdb')
        assert resp.status_code == 404

    def test_file_not_found(self, client, mock_proxy):
        mock_proxy.find_subfolder.return_value = 'folder_abc'
        mock_proxy.find_file.return_value = None
        resp = client.get('/jp/stocks_daily/1234.duckdb')
        assert resp.status_code == 404

    def test_listed_info_uses_root(self, client, mock_proxy):
        mock_proxy.find_file.return_value = 'file_123'
        from flask import Response
        mock_proxy.stream_file.return_value = Response(
            b'data', content_type='application/octet-stream'
        )
        resp = client.get('/jp/listed_info.duckdb')
        assert resp.status_code == 200
        # サブフォルダなしの場合は root_folder_id を使う
        mock_proxy.find_file.assert_called_with(mock_proxy.root_folder_id, 'listed_info.duckdb')

    def test_stocks_board_valid(self, client, mock_proxy):
        mock_proxy.find_subfolder.return_value = 'folder_board'
        mock_proxy.find_file.return_value = 'file_456'
        from flask import Response
        mock_proxy.stream_file.return_value = Response(
            b'data', content_type='application/octet-stream'
        )
        resp = client.get('/jp/stocks_board/8306.duckdb')
        assert resp.status_code == 200


# ===========================================================================
# TestUploadRoute
# ===========================================================================

class TestUploadRoute:
    """POST /jp/<path>"""

    def test_upload_success(self, client, mock_proxy):
        mock_proxy.find_subfolder.return_value = 'folder_abc'
        mock_proxy.upload_file.return_value = 'file_id_123'

        with patch.dict(os.environ, {'UPLOAD_API_KEY': 'secret'}):
            resp = client.post(
                '/jp/stocks_daily/1234.duckdb',
                data=b'duckdb_data',
                headers={'X-API-Key': 'secret'},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['file_id'] == 'file_id_123'

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

    def test_subfolder_not_found_returns_404(self, client, mock_proxy):
        mock_proxy.find_subfolder.return_value = None
        with patch.dict(os.environ, {'UPLOAD_API_KEY': 'secret'}):
            resp = client.post(
                '/jp/stocks_daily/1234.duckdb',
                data=b'data',
                headers={'X-API-Key': 'secret'},
            )
        assert resp.status_code == 404

    def test_listed_info_single_part_returns_400(self, client, mock_proxy):
        with patch.dict(os.environ, {'UPLOAD_API_KEY': 'secret'}):
            resp = client.post(
                '/jp/listed_info.duckdb',
                data=b'data',
                headers={'X-API-Key': 'secret'},
            )
        assert resp.status_code == 400

    def test_upload_sends_correct_data(self, client, mock_proxy):
        mock_proxy.find_subfolder.return_value = 'folder_abc'
        mock_proxy.upload_file.return_value = 'file_id'

        with patch.dict(os.environ, {'UPLOAD_API_KEY': 'secret'}):
            client.post(
                '/jp/stocks_daily/1234.duckdb',
                data=b'my_duckdb_content',
                headers={'X-API-Key': 'secret'},
            )
        mock_proxy.upload_file.assert_called_once_with(
            'folder_abc', '1234.duckdb', b'my_duckdb_content'
        )


# ===========================================================================
# TestErrorHandlers
# ===========================================================================

class TestErrorHandlers:
    """Flask エラーハンドラ"""

    def test_google_http_error_404(self, client, mock_proxy):
        from googleapiclient.errors import HttpError
        resp_mock = MagicMock()
        resp_mock.status = 404
        mock_proxy.find_subfolder.side_effect = HttpError(resp_mock, b'Not Found')

        resp = client.get('/jp/stocks_daily/1234.duckdb')
        assert resp.status_code == 404

    def test_google_http_error_500(self, client, mock_proxy):
        from googleapiclient.errors import HttpError
        resp_mock = MagicMock()
        resp_mock.status = 500
        mock_proxy.find_subfolder.side_effect = HttpError(resp_mock, b'Server Error')

        resp = client.get('/jp/stocks_daily/1234.duckdb')
        assert resp.status_code == 503

    def test_unexpected_exception(self, client, mock_proxy):
        mock_proxy.find_subfolder.side_effect = RuntimeError("boom")

        resp = client.get('/jp/stocks_daily/1234.duckdb')
        assert resp.status_code == 500
        assert b'Internal error' in resp.data
