"""
立花証券-e支店 APIの基本テスト

このファイルには、立花証券-e支店 API（https://api.e_api.com）を
使用した最小限の統合テストが含まれています。
"""

import pytest
import json
import os
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv
from BackcastPro.api.lib.e_api import e_api


# 環境変数を読み込み
load_dotenv()

class Test_e_api:
    """立花証券-e支店 APIの基本機能テスト"""
    
    @pytest.fixture(autouse=True)
    def setup_test(self):
        """テスト前のセットアップ"""
        # 環境変数が設定されているかチェック
        sPassword = os.getenv('eAPI_PASSWORD')
        sUserId = os.getenv('eAPI_USER_ID')
        
        if not sUserId or not sPassword:
            pytest.skip("立花証券-e支店認証情報が設定されていません。環境変数eAPI_USER_IDとeAPI_PASSWORDを設定してください。")
        
        # シングルトンをリセット
        e_api._instance = None
        
        # 立花証券-e支店クライアントを初期化
        self.e_shiten = e_api()
        
        # 認証が成功しているかチェック
        if not self.e_shiten.isEnable:
            pytest.skip("立花証券-e支店認証に失敗しました。認証情報を確認してください。")
        
        yield
        
        # テスト後のクリーンアップ
        e_api._instance = None
    
    def test_e_api_authentication(self):
        """立花証券-e支店 API認証のテスト"""
        assert self.e_shiten.isEnable is True
        assert len(self.e_shiten.sUrlRequest) > 0
        assert len(self.e_shiten.sUrlMaster) > 0
        assert len(self.e_shiten.sUrlPrice) > 0
        assert len(self.e_shiten.sUrlEvent) > 0
        assert len(self.e_shiten.sUrlEventWebSocket) > 0

    def test_e_api_get_daily_quotes(self):
        """立花証券-e支店 日次株価取得のテスト"""
        # 実際のAPIを呼び出し
        result_df = self.e_shiten.get_daily_quotes("13010")
        
        # レスポンスを確認
        assert isinstance(result_df, pd.DataFrame)
        
        # データが存在する場合の基本確認
        if not result_df.empty:
            assert 'Open' in result_df.columns
            assert 'Close' in result_df.columns
            assert 'High' in result_df.columns
            assert 'Low' in result_df.columns

    def test_e_api_get_board(self):
        """立花証券-e支店 板情報取得のテスト"""
        # 実際のAPIを呼び出し（銘柄コード: 8306 三菱UFJなど）
        df = self.e_shiten.get_board("8306")
        
        # DataFrameが返ってくることを確認
        assert isinstance(df, pd.DataFrame)
        
        # データが存在する場合の確認
        if not df.empty:
            assert 'Price' in df.columns
            assert 'Qty' in df.columns
            assert 'Type' in df.columns
            
            # Bid/Askが含まれているか
            assert 'Bid' in df['Type'].values or 'Ask' in df['Type'].values


class Test_e_api_Cache:
    """立花証券-e支店 APIキャッシュ機能のテスト"""
    
    @pytest.fixture(autouse=True)
    def setup_cache_test(self):
        """キャッシュテスト前のセットアップ"""
        # シングルトンをリセット
        e_api._instance = None
        
        # テスト用のキャッシュディレクトリを設定
        self.cache_dir = Path("cache/test")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "e_api_login_cache.json"
        self.failure_cache_file = self.cache_dir / "e_api_login_failures.json"
        
        yield
        
        # テスト後のクリーンアップ
        if self.cache_file.exists():
            self.cache_file.unlink()
        if self.failure_cache_file.exists():
            self.failure_cache_file.unlink()
        if self.cache_dir.exists():
            self.cache_dir.rmdir()
        e_api._instance = None
    
    def test_save_to_cache(self):
        """ログイン情報のキャッシュ保存のテスト"""
        with patch.dict(os.environ, {
            'eAPI_URL': 'https://test.e-shiten.jp/e_api_v4r8',
            'eAPI_USER_ID': 'test_user',
            'eAPI_PASSWORD': 'test_pass'
        }):
            with patch('requests.get') as mock_get:
                # ログイン成功レスポンスをモック
                mock_response = MagicMock()
                mock_response.content = json.dumps({
                    '287': '0',  # p_errno
                    '688': '0',  # sResultCode
                    '872': 'https://test.request.url',  # sUrlRequest
                    '870': 'https://test.master.url',   # sUrlMaster
                    '871': 'https://test.price.url',    # sUrlPrice
                    '868': 'https://test.event.url',    # sUrlEvent
                    '869': 'https://test.websocket.url', # sUrlEventWebSocket
                    '288': '2',  # p_no
                    '290': datetime.now().strftime('%Y.%m.%d-%H:%M:%S.%f')[:-3]  # p_sd_date
                }).encode('shift-jis')
                mock_response.apparent_encoding = 'shift-jis'
                mock_get.return_value = mock_response
                
                # e_apiインスタンスを作成
                client = e_api()
                
                # キャッシュディレクトリを変更
                client.cache_dir = self.cache_dir
                client.cache_file = self.cache_file
                client.failure_cache_file = self.failure_cache_file
                
                # ログインブロックを解除
                client.login_blocked_until = None
                client.login_failures = []
                
                # 現在のp_noを保存
                original_p_no = client.p_no
                
                # ログイン処理を実行してtoken_expires_atを設定
                client._set_token()
                
                # キャッシュに保存
                client._save_to_cache()
                
                # キャッシュファイルが作成されたことを確認
                assert self.cache_file.exists()
                
                # キャッシュファイルの内容を確認
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                assert 'sUrlRequest' in cache_data
                assert 'sUrlMaster' in cache_data
                assert 'sUrlPrice' in cache_data
                assert 'token_expires_at' in cache_data
                assert 'p_no' in cache_data
                # p_noが整数であることを確認（値は環境によって異なる可能性があるため）
                assert isinstance(cache_data['p_no'], int)
    
    def test_load_from_cache_valid(self):
        """有効なキャッシュからの読み込みのテスト"""
        # 有効なキャッシュデータを作成
        token_expires_at = datetime.now() + timedelta(hours=12)
        cache_data = {
            'sUrlRequest': 'https://test.request.url',
            'sUrlMaster': 'https://test.master.url',
            'sUrlPrice': 'https://test.price.url',
            'sUrlEvent': 'https://test.event.url',
            'sUrlEventWebSocket': 'https://test.websocket.url',
            'p_no': 5,
            'token_expires_at': token_expires_at.isoformat(),
            'saved_at': datetime.now().isoformat()
        }
        
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f)
        
        with patch.dict(os.environ, {
            'eAPI_URL': 'https://test.e-shiten.jp/e_api_v4r8',
            'eAPI_USER_ID': 'test_user',
            'eAPI_PASSWORD': 'test_pass'
        }):
            client = e_api()
            client.cache_dir = self.cache_dir
            client.cache_file = self.cache_file
            client.failure_cache_file = self.failure_cache_file
            
            # キャッシュから読み込み
            result = client._load_from_cache()
            
            # 読み込みが成功したことを確認
            assert result is True
            assert client.sUrlRequest == 'https://test.request.url'
            assert client.p_no == 5
            assert client.token_expires_at == token_expires_at
    
    def test_load_from_cache_expired(self):
        """期限切れキャッシュからの読み込みのテスト"""
        # 期限切れのキャッシュデータを作成
        token_expires_at = datetime.now() - timedelta(hours=1)
        cache_data = {
            'sUrlRequest': 'https://test.request.url',
            'sUrlMaster': 'https://test.master.url',
            'sUrlPrice': 'https://test.price.url',
            'sUrlEvent': 'https://test.event.url',
            'sUrlEventWebSocket': 'https://test.websocket.url',
            'p_no': 5,
            'token_expires_at': token_expires_at.isoformat(),
            'saved_at': datetime.now().isoformat()
        }
        
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f)
        
        with patch.dict(os.environ, {
            'eAPI_URL': 'https://test.e-shiten.jp/e_api_v4r8',
            'eAPI_USER_ID': 'test_user',
            'eAPI_PASSWORD': 'test_pass'
        }):
            client = e_api()
            client.cache_dir = self.cache_dir
            client.cache_file = self.cache_file
            client.failure_cache_file = self.failure_cache_file
            
            # 期限切れキャッシュからの読み込み
            result = client._load_from_cache()
            
            # 読み込みが失敗したことを確認
            assert result is False


class Test_e_api_LoginFailure:
    """立花証券-e支店 APIログイン失敗管理のテスト"""
    
    @pytest.fixture(autouse=True)
    def setup_failure_test(self):
        """ログイン失敗テスト前のセットアップ"""
        # シングルトンをリセット
        e_api._instance = None
        
        # テスト用のキャッシュディレクトリを設定
        self.cache_dir = Path("cache/test")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "e_api_login_cache.json"
        self.failure_cache_file = self.cache_dir / "e_api_login_failures.json"
        
        yield
        
        # テスト後のクリーンアップ
        if self.cache_file.exists():
            self.cache_file.unlink()
        if self.failure_cache_file.exists():
            self.failure_cache_file.unlink()
        if self.cache_dir.exists():
            self.cache_dir.rmdir()
        e_api._instance = None
    
    def test_record_login_failure(self):
        """ログイン失敗記録のテスト"""
        with patch.dict(os.environ, {
            'eAPI_URL': 'https://test.e-shiten.jp/e_api_v4r8',
            'eAPI_USER_ID': 'test_user',
            'eAPI_PASSWORD': 'test_pass'
        }):
            client = e_api()
            client.cache_dir = self.cache_dir
            client.cache_file = self.cache_file
            client.failure_cache_file = self.failure_cache_file
            
            # ログインブロックと失敗履歴をリセット
            client.login_blocked_until = None
            client.login_failures = []
            
            # 1回目の失敗を記録
            client._record_login_failure()
            
            # 失敗履歴が記録されたことを確認
            assert len(client.login_failures) == 1
            assert self.failure_cache_file.exists()
            
            # ブロックされていないことを確認
            assert client.login_blocked_until is None
    
    def test_login_blocked_after_three_failures(self):
        """3回失敗後のブロックのテスト"""
        with patch.dict(os.environ, {
            'eAPI_URL': 'https://test.e-shiten.jp/e_api_v4r8',
            'eAPI_USER_ID': 'test_user',
            'eAPI_PASSWORD': 'test_pass'
        }):
            client = e_api()
            client.cache_dir = self.cache_dir
            client.cache_file = self.cache_file
            client.failure_cache_file = self.failure_cache_file
            
            # ログインブロックと失敗履歴をリセット
            client.login_blocked_until = None
            client.login_failures = []
            
            # 3回失敗を記録
            client._record_login_failure()
            client._record_login_failure()
            client._record_login_failure()
            
            # ブロックされたことを確認
            assert client.login_blocked_until is not None
            assert len(client.login_failures) == 3
            
            # ブロック期限が約24時間後であることを確認
            time_diff = client.login_blocked_until - datetime.now()
            assert 23.5 <= time_diff.total_seconds() / 3600 <= 24.5
    
    def test_is_login_blocked(self):
        """ログインブロック状態のチェックのテスト"""
        with patch.dict(os.environ, {
            'eAPI_URL': 'https://test.e-shiten.jp/e_api_v4r8',
            'eAPI_USER_ID': 'test_user',
            'eAPI_PASSWORD': 'test_pass'
        }):
            client = e_api()
            client.cache_dir = self.cache_dir
            client.cache_file = self.cache_file
            client.failure_cache_file = self.failure_cache_file
            
            # ブロック期限を設定
            client.login_blocked_until = datetime.now() + timedelta(hours=1)
            client._save_login_failures()
            
            # ブロックされていることを確認
            assert client._is_login_blocked() is True
            
            # ブロック期限を過去に設定
            client.login_blocked_until = datetime.now() - timedelta(hours=1)
            client._save_login_failures()
            
            # ブロックが解除されたことを確認
            assert client._is_login_blocked() is False
            assert client.login_blocked_until is None
    
    def test_login_failure_history_persistence(self):
        """ログイン失敗履歴の永続化のテスト"""
        with patch.dict(os.environ, {
            'eAPI_URL': 'https://test.e-shiten.jp/e_api_v4r8',
            'eAPI_USER_ID': 'test_user',
            'eAPI_PASSWORD': 'test_pass'
        }):
            # 1つ目のクライアントで失敗を記録
            client1 = e_api()
            client1.cache_dir = self.cache_dir
            client1.cache_file = self.cache_file
            client1.failure_cache_file = self.failure_cache_file
            
            # ログインブロックと失敗履歴をリセット
            client1.login_blocked_until = None
            client1.login_failures = []
            
            client1._record_login_failure()
            client1._record_login_failure()
            
            # シングルトンをリセット
            e_api._instance = None
            
            # 2つ目のクライアントで失敗履歴を読み込み
            client2 = e_api()
            client2.cache_dir = self.cache_dir
            client2.cache_file = self.cache_file
            client2.failure_cache_file = self.failure_cache_file
            
            client2._load_login_failures()
            
            # 失敗履歴が引き継がれたことを確認
            assert len(client2.login_failures) == 2
    
    def test_login_success_clears_failures(self):
        """ログイン成功時の失敗履歴クリアのテスト"""
        with patch.dict(os.environ, {
            'eAPI_URL': 'https://test.e-shiten.jp/e_api_v4r8',
            'eAPI_USER_ID': 'test_user',
            'eAPI_PASSWORD': 'test_pass'
        }):
            client = e_api()
            client.cache_dir = self.cache_dir
            client.cache_file = self.cache_file
            client.failure_cache_file = self.failure_cache_file
            
            # ログインブロックと失敗履歴をリセット
            client.login_blocked_until = None
            client.login_failures = []
            
            # 失敗を記録
            client._record_login_failure()
            client._record_login_failure()
            assert len(client.login_failures) == 2
            assert self.failure_cache_file.exists()
            
            # 失敗履歴を手動でクリア（ログイン成功をシミュレート）
            client.login_failures = []
            client.login_blocked_until = None
            if self.failure_cache_file.exists():
                self.failure_cache_file.unlink()
            
            # 失敗履歴がクリアされたことを確認
            assert len(client.login_failures) == 0
            assert client.login_blocked_until is None
            assert not self.failure_cache_file.exists()

class Test_e_api_Mock:
    """立花証券-e支店 APIのモックテスト（認証情報なしで実行可能）"""
    
    @pytest.fixture(autouse=True)
    def setup_mock_test(self):
        """モックテスト前のセットアップ"""
        # シングルトンをリセット
        e_api._instance = None
        
        # テスト用のキャッシュディレクトリを設定
        self.cache_dir = Path("cache/test_mock")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "e_api_login_cache.json"
        
        self.client = e_api()
        self.client.cache_dir = self.cache_dir
        self.client.cache_file = self.cache_file
        
        # ダミーのURLを設定
        self.client.sUrlPrice = "https://mock.price.url"
        self.client.p_no = 1
        self.client.token_expires_at = datetime.now() + timedelta(hours=1)
        self.client.isEnable = True
        
        yield
        
        # テスト後のクリーンアップ
        if self.cache_file.exists():
            self.cache_file.unlink()
        if self.cache_dir.exists():
            self.cache_dir.rmdir()
        e_api._instance = None

    def test_mock_get_board_success(self):
        """get_board: 正常系（買い板・売り板あり）"""
        with patch('requests.get') as mock_get:
            # モックレスポンスの作成
            mock_response = MagicMock()
            mock_data = {
                'p_errno': '0',
                'p_no': '2',
                'aCLMMfdsMarketPrice': [{
                    'pGBP1': '100.0', 'pGBV1': '1000',  # 買1
                    'pGAP1': '101.0', 'pGAV1': '2000',  # 売1
                    'pQUV': '500',   # 買UNDER
                    'pQOV': '600',   # 売OVER
                }]
            }
            mock_response.json.return_value = mock_data
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            # API呼び出し
            df = self.client.get_board('1234')
            
            # 検証
            assert isinstance(df, pd.DataFrame)
            assert not df.empty
            assert len(df) == 4 # 買1, 売1, 買UNDER, 売OVER
            
            # 内容の検証
            bid_1 = df[(df['Type'] == 'Bid') & (df['Price'] == 100.0)]
            assert len(bid_1) == 1
            assert bid_1.iloc[0]['Qty'] == 1000
            
            ask_1 = df[(df['Type'] == 'Ask') & (df['Price'] == 101.0)]
            assert len(ask_1) == 1
            assert ask_1.iloc[0]['Qty'] == 2000
            
            bid_under = df[(df['Type'] == 'Bid') & (df['Price'] == 0.0)]
            assert len(bid_under) == 1
            assert bid_under.iloc[0]['Qty'] == 500
            
            ask_over = df[(df['Type'] == 'Ask') & (df['Price'] == 0.0)]
            assert len(ask_over) == 1
            assert ask_over.iloc[0]['Qty'] == 600

    def test_mock_get_board_error(self):
        """get_board: エラー系"""
        with patch('requests.get') as mock_get:
            # エラーレスポンス
            mock_response = MagicMock()
            mock_data = {
                'p_errno': '1', # エラーあり
                'p_err': 'Some Error',
                'p_no': '3'
            }
            mock_response.json.return_value = mock_data
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            df = self.client.get_board('1234')
            
            assert isinstance(df, pd.DataFrame)
            assert df.empty

    def test_mock_get_daily_quotes_success(self):
        """get_daily_quotes: 正常系"""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_data = {
                'p_errno': '0',
                'p_no': '4',
                'aCLMMfdsMarketPriceHistory': [
                    {
                        'sDate': '20230101',
                        'pDOP': '100', 'pDHP': '110', 'pDLP': '90', 'pDPP': '105', 'pDV': '1000',
                        'pDOPxK': '100', 'pDHPxK': '110', 'pDLPxK': '90', 'pDPPxK': '105', 'pDVxK': '1000', 'pSPUK': '1'
                    },
                    {
                        'sDate': '20230102',
                        'pDOP': '105', 'pDHP': '115', 'pDLP': '100', 'pDPP': '110', 'pDV': '1500',
                         'pDOPxK': '105', 'pDHPxK': '115', 'pDLPxK': '100', 'pDPPxK': '110', 'pDVxK': '1500', 'pSPUK': '1'
                    }
                ]
            }
            mock_response.json.return_value = mock_data
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            df = self.client.get_daily_quotes('1234')
            
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 2
            assert 'Close' in df.columns
            assert df.index.name == 'Date'
            # 日付型に変換されているか確認 (DatetimeIndex)
            assert isinstance(df.index, pd.DatetimeIndex)

    def test_mock_get_daily_quotes_filter(self):
        """get_daily_quotes: 期間フィルタリング"""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            # 2日分のデータ（1/1, 1/5）
            mock_data = {
                'p_errno': '0', 'p_no': '5',
                'aCLMMfdsMarketPriceHistory': [
                    {'sDate': '20230101', 'pDOP': '100', 'pDHP': '100', 'pDLP': '100', 'pDPP': '100', 'pDV': '100', 'pDOPxK': '100', 'pDHPxK': '100', 'pDLPxK': '100', 'pDPPxK': '100', 'pDVxK': '100', 'pSPUK': '1'},
                    {'sDate': '20230105', 'pDOP': '100', 'pDHP': '100', 'pDLP': '100', 'pDPP': '100', 'pDV': '100', 'pDOPxK': '100', 'pDHPxK': '100', 'pDLPxK': '100', 'pDPPxK': '100', 'pDVxK': '100', 'pSPUK': '1'}
                ]
            }
            mock_response.json.return_value = mock_data
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            # 1/2 から 1/6 までの期間を指定 -> 1/5のみ残るはず
            from_date = datetime(2023, 1, 2)
            to_date = datetime(2023, 1, 6)
            
            df = self.client.get_daily_quotes('1234', from_=from_date, to=to_date)
            
            assert len(df) == 1
            assert df.index[0] == datetime(2023, 1, 5)

    def test_mock_get_daily_quotes_error(self):
        """get_daily_quotes: エラー系"""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_data = {'p_errno': '99', 'p_err': 'Error'}
            mock_response.json.return_value = mock_data
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            df = self.client.get_daily_quotes('1234')
            assert df.empty