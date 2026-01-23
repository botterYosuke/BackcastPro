"""
Stooqモジュールの基本テスト

このファイルには、lib.stooqモジュールの単体テストと統合テストが含まれています。
"""

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
import pandas as pd
import numpy as np

# Ensure src is in pythonpath
sys.path.insert(0, os.path.abspath('src'))

from BackcastPro.api.lib.stooq import (
    stooq_daily_quotes,
    _stooq_normalize_columns,
    _add_adjustment_prices,
    _add_price_limits,
    _get_yfinance_daily_quotes
)


class TestStooqDataRetrieval:
    """Stooqデータ取得機能のテスト"""
    
    def create_sample_stooq_dataframe(self):
        """テスト用のサンプルDataFrameを作成"""
        dates = pd.date_range(start='2024-01-01', periods=5, freq='D')
        data = {
            'Open': [100.0, 102.0, 101.0, 103.0, 105.0],
            'High': [105.0, 107.0, 106.0, 108.0, 110.0],
            'Low': [98.0, 100.0, 99.0, 101.0, 103.0],
            'Close': [103.0, 105.0, 104.0, 106.0, 108.0],
            'Volume': [1000000, 1200000, 1100000, 1300000, 1400000],
            'Adj Close': [103.0, 105.0, 104.0, 106.0, 108.0]
        }
        df = pd.DataFrame(data, index=dates)
        return df
    
    @patch('BackcastPro.api.lib.stooq.yf')
    def test_stooq_daily_quotes_success(self, mock_yf):
        """正常にデータが取得できる場合のテスト"""
        # モックデータを準備
        mock_df = self.create_sample_stooq_dataframe()
        mock_yf.download.return_value = mock_df

        # テスト実行
        result = stooq_daily_quotes('7203', datetime(2024, 1, 1), datetime(2024, 1, 5))

        # 検証
        assert result is not None
        assert len(result) == 5
        assert 'Date' in result.columns or isinstance(result.index, pd.DatetimeIndex)
        mock_yf.download.assert_called_once()
    
    @patch('BackcastPro.api.lib.stooq.yf')
    @patch('BackcastPro.api.lib.stooq._get_yfinance_daily_quotes')
    def test_stooq_daily_quotes_empty(self, mock_yfinance_api, mock_yf):
        """空のDataFrameが返される場合のテスト"""
        # 空のDataFrameを返すモック
        mock_yf.download.return_value = pd.DataFrame()
        mock_yfinance_api.return_value = pd.DataFrame()

        # テスト実行
        result = stooq_daily_quotes('9999', datetime(2024, 1, 1), datetime(2024, 1, 5))

        # 検証（空のDataFrameが返される）
        assert result.empty

    @patch('BackcastPro.api.lib.stooq.yf')
    def test_stooq_daily_quotes_error(self, mock_yf):
        """エラーが発生した場合のテスト"""
        # 例外を発生させるモック
        mock_yf.download.side_effect = Exception("API Error")

        # テスト実行
        result = stooq_daily_quotes('7203', datetime(2024, 1, 1), datetime(2024, 1, 5))

        # 検証（エラー時は空のDataFrameが返される）
        assert result.empty


class TestStooqNormalization:
    """Stooqデータ正規化機能のテスト"""
    
    def create_sample_stooq_dataframe(self):
        """テスト用のサンプルDataFrameを作成"""
        dates = pd.date_range(start='2024-01-01', periods=5, freq='D')
        data = {
            'Open': [100.0, 102.0, 101.0, 103.0, 105.0],
            'High': [105.0, 107.0, 106.0, 108.0, 110.0],
            'Low': [98.0, 100.0, 99.0, 101.0, 103.0],
            'Close': [103.0, 105.0, 104.0, 106.0, 108.0],
            'Volume': [1000000, 1200000, 1100000, 1300000, 1400000],
            'Adj Close': [103.0, 105.0, 104.0, 106.0, 108.0]
        }
        df = pd.DataFrame(data, index=dates)
        return df
    
    def test_stooq_normalize_columns(self):
        """カラム正規化のテスト"""
        # サンプルデータを準備
        df = self.create_sample_stooq_dataframe()

        # テスト実行
        result = _stooq_normalize_columns('7203', df)

        # 検証 - インデックスがDatetimeIndexであることを確認
        assert isinstance(result.index, pd.DatetimeIndex)

        # カラムの確認
        assert 'Code' in result.columns
        assert 'Open' in result.columns
        assert 'High' in result.columns
        assert 'Low' in result.columns
        assert 'Close' in result.columns
        assert 'Volume' in result.columns
        assert 'AdjustmentClose' in result.columns
        assert 'TurnoverValue' in result.columns
        assert 'AdjustmentFactor' in result.columns
        assert 'AdjustmentOpen' in result.columns
        assert 'AdjustmentHigh' in result.columns
        assert 'AdjustmentLow' in result.columns
        assert 'AdjustmentVolume' in result.columns
        assert 'UpperLimit' in result.columns
        assert 'LowerLimit' in result.columns

        # Codeカラムの値を確認
        assert all(result['Code'] == '7203')
    
    def test_add_adjustment_prices(self):
        """調整価格計算のテスト"""
        # サンプルデータを準備
        dates = pd.date_range(start='2024-01-01', periods=3, freq='D')
        data = {
            'Open': [100.0, 102.0, 101.0],
            'High': [105.0, 107.0, 106.0],
            'Low': [98.0, 100.0, 99.0],
            'Close': [103.0, 105.0, 104.0],
            'Volume': [1000000, 1200000, 1100000],
            'AdjustmentClose': [103.0, 105.0, 104.0]
        }
        df = pd.DataFrame(data, index=dates)
        
        # テスト実行
        result = _add_adjustment_prices(df)
        
        # 検証
        assert 'AdjustmentFactor' in result.columns
        assert 'AdjustmentOpen' in result.columns
        assert 'AdjustmentHigh' in result.columns
        assert 'AdjustmentLow' in result.columns
        assert 'AdjustmentVolume' in result.columns
        
        # 調整係数が正しく計算されているか
        expected_factor = result['AdjustmentClose'] / result['Close']
        pd.testing.assert_series_equal(result['AdjustmentFactor'], expected_factor, check_names=False)
        
        # 調整価格が正しく計算されているか
        expected_adj_open = result['Open'] * result['AdjustmentFactor']
        pd.testing.assert_series_equal(result['AdjustmentOpen'], expected_adj_open, check_names=False)
    
    def test_add_adjustment_prices_with_split(self):
        """株式分割を含む調整価格計算のテスト"""
        # 2:1の株式分割を想定したデータ
        dates = pd.date_range(start='2024-01-01', periods=3, freq='D')
        data = {
            'Open': [100.0, 50.0, 51.0],  # 分割後は価格が半分
            'High': [105.0, 55.0, 56.0],
            'Low': [98.0, 48.0, 49.0],
            'Close': [103.0, 52.0, 53.0],
            'Volume': [1000000, 2000000, 2100000],  # 分割後は出来高が倍
            'AdjustmentClose': [51.5, 52.0, 53.0]  # 調整済終値
        }
        df = pd.DataFrame(data, index=dates)
        
        # テスト実行
        result = _add_adjustment_prices(df)
        
        # 検証
        assert 'AdjustmentFactor' in result.columns
        # 調整係数が計算されているか
        assert not result['AdjustmentFactor'].isnull().any()
    
    def test_add_price_limits(self):
        """値幅制限計算のテスト"""
        # サンプルデータを準備
        dates = pd.date_range(start='2024-01-01', periods=5, freq='D')
        data = {
            'Close': [1000.0, 1050.0, 1020.0, 1080.0, 1100.0]
        }
        df = pd.DataFrame(data, index=dates)
        
        # テスト実行
        result = _add_price_limits(df)
        
        # 検証
        assert 'UpperLimit' in result.columns
        assert 'LowerLimit' in result.columns
        
        # 初日はNoneであること
        assert pd.isna(result['UpperLimit'].iloc[0])
        assert pd.isna(result['LowerLimit'].iloc[0])
        
        # 2日目以降は値が設定されていること
        assert not pd.isna(result['UpperLimit'].iloc[1])
        assert not pd.isna(result['LowerLimit'].iloc[1])
        
        # 値幅制限が前日終値を基準に正しく計算されているか
        # 1000円の場合、値幅は300円（1000-1500円のレンジ）
        assert result['UpperLimit'].iloc[1] == 1300.0
        assert result['LowerLimit'].iloc[1] == 700.0
    
    def test_add_price_limits_various_prices(self):
        """様々な価格帯での値幅制限計算のテスト"""
        # 異なる価格帯でのテスト
        test_cases = [
            (50.0, 30),      # 100円未満 -> 30円
            (150.0, 50),     # 100-200円 -> 50円
            (300.0, 80),     # 200-500円 -> 80円
            (600.0, 100),    # 500-700円 -> 100円
            (800.0, 150),    # 700-1000円 -> 150円
            (1200.0, 300),   # 1000-1500円 -> 300円
            (1800.0, 400),   # 1500-2000円 -> 400円
            (2500.0, 500),   # 2000-3000円 -> 500円
            (4000.0, 700),   # 3000-5000円 -> 700円
            (6000.0, 1000),  # 5000-7000円 -> 1000円
        ]
        
        for price, expected_width in test_cases:
            dates = pd.date_range(start='2024-01-01', periods=2, freq='D')
            data = {'Close': [price, price + 10]}
            df = pd.DataFrame(data, index=dates)
            
            result = _add_price_limits(df)
            
            # 2日目の値幅制限をチェック
            expected_upper = round(price + expected_width, 1)
            expected_lower = round(price - expected_width, 1)
            
            assert result['UpperLimit'].iloc[1] == expected_upper, \
                f"価格{price}円のストップ高が不正: {result['UpperLimit'].iloc[1]} != {expected_upper}"
            assert result['LowerLimit'].iloc[1] == expected_lower, \
                f"価格{price}円のストップ安が不正: {result['LowerLimit'].iloc[1]} != {expected_lower}"


class TestYFinanceAPI:
    """Yahoo Finance API関連のテスト"""
    
    @patch('BackcastPro.api.lib.stooq.requests.get')
    def test_get_yfinance_daily_quotes_success(self, mock_get):
        """Yahoo Finance APIからの正常なデータ取得のテスト"""
        # モックレスポンスを準備
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'chart': {
                'result': [{
                    'timestamp': [1704067200, 1704153600, 1704240000],  # 2024-01-01, 02, 03のタイムスタンプ
                    'indicators': {
                        'quote': [{
                            'open': [100.0, 102.0, 101.0],
                            'high': [105.0, 107.0, 106.0],
                            'low': [98.0, 100.0, 99.0],
                            'close': [103.0, 105.0, 104.0],
                            'volume': [1000000, 1200000, 1100000]
                        }],
                        'adjclose': [{
                            'adjclose': [103.0, 105.0, 104.0]
                        }]
                    }
                }]
            }
        }
        mock_get.return_value = mock_response
        
        # テスト実行
        result = _get_yfinance_daily_quotes('7203', datetime(2024, 1, 1), datetime(2024, 1, 3))
        
        # 検証
        assert not result.empty
        assert len(result) == 3
        assert 'Open' in result.columns
        assert 'Close' in result.columns
        assert 'Adj Close' in result.columns
        mock_get.assert_called_once()
    
    @patch('BackcastPro.api.lib.stooq.requests.get')
    def test_get_yfinance_daily_quotes_error(self, mock_get):
        """Yahoo Finance APIエラー時のテスト"""
        # エラーレスポンスを準備
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        # テスト実行
        result = _get_yfinance_daily_quotes('9999', datetime(2024, 1, 1), datetime(2024, 1, 3))
        
        # 検証（エラー時は空のDataFrameが返される）
        assert result.empty
    
    @patch('BackcastPro.api.lib.stooq.requests.get')
    def test_get_yfinance_daily_quotes_no_data(self, mock_get):
        """Yahoo Finance APIからデータが返されない場合のテスト"""
        # データがないレスポンスを準備
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'chart': {
                'result': []
            }
        }
        mock_get.return_value = mock_response
        
        # テスト実行
        result = _get_yfinance_daily_quotes('9999', datetime(2024, 1, 1), datetime(2024, 1, 3))
        
        # 検証
        assert result.empty
    
    @patch('BackcastPro.api.lib.stooq.requests.get')
    def test_get_yfinance_daily_quotes_timeout(self, mock_get):
        """Yahoo Finance APIタイムアウト時のテスト"""
        # タイムアウト例外を発生させる
        import requests
        mock_get.side_effect = requests.exceptions.Timeout("Timeout")
        
        # テスト実行
        result = _get_yfinance_daily_quotes('7203', datetime(2024, 1, 1), datetime(2024, 1, 3))
        
        # 検証（タイムアウト時は空のDataFrameが返される）
        assert result.empty
    
    @patch('BackcastPro.api.lib.stooq.requests.get')
    def test_get_yfinance_daily_quotes_without_adjclose(self, mock_get):
        """Adj Closeがない場合のテスト"""
        # Adj Closeなしのモックレスポンス
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'chart': {
                'result': [{
                    'timestamp': [1704067200, 1704153600],
                    'indicators': {
                        'quote': [{
                            'open': [100.0, 102.0],
                            'high': [105.0, 107.0],
                            'low': [98.0, 100.0],
                            'close': [103.0, 105.0],
                            'volume': [1000000, 1200000]
                        }]
                    }
                }]
            }
        }
        mock_get.return_value = mock_response
        
        # テスト実行
        result = _get_yfinance_daily_quotes('7203', datetime(2024, 1, 1), datetime(2024, 1, 2))
        
        # 検証（Adj CloseがCloseと同じ値になる）
        assert not result.empty
        assert 'Adj Close' in result.columns
        pd.testing.assert_series_equal(result['Close'], result['Adj Close'], check_names=False)


class TestStooqIntegration:
    """Stooqモジュールの統合テスト（実際のAPIを使用）"""
    
    @pytest.mark.integration
    def test_stooq_daily_quotes_real_api(self):
        """実際のAPIを使用したデータ取得テスト"""
        # スキップ可能にする（CIで実行しない場合）
        pytest.skip("実際のAPIを使用するため、通常はスキップします。手動テスト時のみ実行してください。")

        # 実際のAPIを呼び出し
        result = stooq_daily_quotes('7203', datetime(2024, 1, 1), datetime(2024, 1, 10))

        # 検証
        if not result.empty:
            assert 'Open' in result.columns or 'Open' in result.index.names
            assert 'Close' in result.columns or isinstance(result.index, pd.DatetimeIndex)

