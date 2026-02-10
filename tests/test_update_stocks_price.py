"""tests for cloud-job/update_stocks_price.py"""
import os
import sys
import logging
import argparse
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

# cloud-job/ はパッケージ外なので sys.path に追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'cloud-job')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import update_stocks_price as usp
from update_stocks_price import parse_arguments, merge_jquants_priority


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_price_df(dates, close_values, code="7203"):
    """テスト用の株価DataFrameを作成"""
    return pd.DataFrame({
        'Date': pd.to_datetime(dates),
        'Open': close_values,
        'High': close_values,
        'Low': close_values,
        'Close': close_values,
        'Volume': [1000] * len(dates),
        'Code': [code] * len(dates),
    })


# ===========================================================================
# TestParseArguments
# ===========================================================================

class TestParseArguments:
    """CLI引数のパース"""

    def test_defaults(self):
        with patch('sys.argv', ['update_stocks_price.py']):
            args = parse_arguments()
        assert args.codes is None
        assert args.days == 7

    def test_codes_argument(self):
        with patch('sys.argv', ['prog', '--codes', '7203,8306']):
            args = parse_arguments()
        assert args.codes == '7203,8306'

    def test_days_custom(self):
        with patch('sys.argv', ['prog', '--days', '30']):
            args = parse_arguments()
        assert args.days == 30


# ===========================================================================
# TestMergeJquantsPriority
# ===========================================================================

class TestMergeJquantsPriority:
    """J-Quants優先マージ"""

    def test_base_none_returns_jquants(self):
        jq_df = _make_price_df(['2024-01-01', '2024-01-02'], [200, 201])
        result = merge_jquants_priority(None, jq_df)
        assert len(result) == 2

    def test_base_empty_returns_jquants(self):
        jq_df = _make_price_df(['2024-01-01'], [200])
        result = merge_jquants_priority(pd.DataFrame(), jq_df)
        assert len(result) == 1

    def test_jquants_none_returns_base(self):
        base_df = _make_price_df(['2024-01-01'], [100])
        result = merge_jquants_priority(base_df, None)
        assert len(result) == 1

    def test_jquants_empty_returns_base(self):
        base_df = _make_price_df(['2024-01-01'], [100])
        result = merge_jquants_priority(base_df, pd.DataFrame())
        assert len(result) == 1

    def test_both_none(self):
        result = merge_jquants_priority(None, None)
        assert result is None

    def test_no_overlap_concatenates(self):
        base = _make_price_df(['2024-01-01', '2024-01-02'], [100, 101])
        jq = _make_price_df(['2024-01-03', '2024-01-04'], [200, 201])
        result = merge_jquants_priority(base, jq)
        assert len(result) == 4

    def test_overlap_jquants_wins(self):
        base = _make_price_df(['2024-01-01'], [100])
        jq = _make_price_df(['2024-01-01'], [200])
        result = merge_jquants_priority(base, jq)
        assert len(result) == 1
        assert result['Close'].iloc[0] == 200

    def test_partial_overlap(self):
        base = _make_price_df(['2024-01-01', '2024-01-02', '2024-01-03'], [100, 101, 102])
        jq = _make_price_df(['2024-01-02', '2024-01-03', '2024-01-04'], [200, 201, 202])
        result = merge_jquants_priority(base, jq)
        assert len(result) == 4
        result_sorted = result.sort_index()
        assert result_sorted['Close'].iloc[1] == 200  # Jan 2
        assert result_sorted['Close'].iloc[2] == 201  # Jan 3

    def test_result_sorted_by_date(self):
        base = _make_price_df(['2024-01-03'], [100])
        jq = _make_price_df(['2024-01-01'], [200])
        result = merge_jquants_priority(base, jq)
        assert result.index.is_monotonic_increasing


# ===========================================================================
# TestMain
# ===========================================================================

class TestMain:
    """main() 統合テスト"""

    @patch('update_stocks_price.stocks_price')
    @patch('update_stocks_price.jquants_cls')
    @patch('update_stocks_price.e_api')
    def test_main_with_codes_success(self, mock_eapi, mock_jq, mock_sp_cls):
        sp = MagicMock()
        mock_sp_cls.return_value = sp
        jq_df = _make_price_df(['2024-01-01'], [200])
        sp._fetch_from_tachibana.return_value = _make_price_df(['2024-01-01'], [100])
        sp._fetch_from_jquants.return_value = jq_df

        with patch('sys.argv', ['prog', '--codes', '7203']):
            result = usp.main()

        assert result == 0
        sp.db.save_stock_prices.assert_called_once()

    @patch('update_stocks_price.stocks_info')
    def test_main_no_codes_returns_1(self, mock_si_cls):
        mock_si = MagicMock()
        mock_si._fetch_from_jquants.return_value = pd.DataFrame()
        mock_si_cls.return_value = mock_si

        with patch('sys.argv', ['prog']):
            result = usp.main()
        assert result == 1

    @patch('update_stocks_price.stocks_price')
    @patch('update_stocks_price.jquants_cls')
    @patch('update_stocks_price.e_api')
    def test_main_all_fail_returns_1(self, mock_eapi, mock_jq, mock_sp_cls):
        sp = MagicMock()
        mock_sp_cls.return_value = sp
        sp._fetch_from_tachibana.side_effect = Exception("fail")
        sp._fetch_from_stooq.side_effect = Exception("fail")
        sp._fetch_from_jquants.side_effect = Exception("fail")

        with patch('sys.argv', ['prog', '--codes', '7203']):
            result = usp.main()
        assert result == 1

    @patch('update_stocks_price.stocks_price')
    @patch('update_stocks_price.jquants_cls')
    @patch('update_stocks_price.e_api')
    def test_stooq_fallback_when_tachibana_fails(self, mock_eapi, mock_jq, mock_sp_cls):
        sp = MagicMock()
        mock_sp_cls.return_value = sp
        sp._fetch_from_tachibana.return_value = None
        sp._fetch_from_stooq.return_value = _make_price_df(['2024-01-01'], [150])
        sp._fetch_from_jquants.return_value = None

        with patch('sys.argv', ['prog', '--codes', '7203']):
            result = usp.main()

        assert result == 0
        sp._fetch_from_stooq.assert_called_once()
        sp.db.save_stock_prices.assert_called_once()
