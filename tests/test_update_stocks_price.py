"""tests for cloud-job/update_stocks_price.py"""
import os
import sys
import logging
import argparse
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call

import pandas as pd
import pytest

# cloud-job/ はパッケージ外なので sys.path に追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'cloud-job')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import update_stocks_price as usp
from update_stocks_price import (
    parse_arguments,
    get_stock_codes_list,
    get_fetch_date_range,
    merge_with_jquants_priority,
    _fetch_with_retry,
    process_stock,
    upload_to_cloud,
    UpdateSummary,
)


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
        assert args.dry_run is False
        assert args.days == 7
        assert args.workers == 4

    def test_codes_argument(self):
        with patch('sys.argv', ['prog', '--codes', '7203,8306']):
            args = parse_arguments()
        assert args.codes == '7203,8306'

    def test_dry_run_flag(self):
        with patch('sys.argv', ['prog', '--dry-run']):
            args = parse_arguments()
        assert args.dry_run is True

    def test_days_custom(self):
        with patch('sys.argv', ['prog', '--days', '30']):
            args = parse_arguments()
        assert args.days == 30

    def test_workers_custom(self):
        with patch('sys.argv', ['prog', '--workers', '8']):
            args = parse_arguments()
        assert args.workers == 8

    def test_all_arguments(self):
        with patch('sys.argv', ['prog', '--codes', '1234', '--dry-run', '--days', '14', '--workers', '2']):
            args = parse_arguments()
        assert args.codes == '1234'
        assert args.dry_run is True
        assert args.days == 14
        assert args.workers == 2


# ===========================================================================
# TestGetStockCodesList
# ===========================================================================

class TestGetStockCodesList:
    """銘柄コードリスト取得・正規化"""

    @patch('update_stocks_price.stocks_info')
    def test_success_with_code_column(self, mock_si_cls):
        mock_si = MagicMock()
        mock_si._fetch_from_jquants.return_value = pd.DataFrame({
            'Code': ['72030', '83060', '1234']
        })
        mock_si_cls.return_value = mock_si
        result = get_stock_codes_list()
        assert result == ['7203', '8306', '1234']

    @patch('update_stocks_price.stocks_info')
    def test_success_with_lowercase_column(self, mock_si_cls):
        mock_si = MagicMock()
        mock_si._fetch_from_jquants.return_value = pd.DataFrame({
            'code': ['72030', '83060']
        })
        mock_si_cls.return_value = mock_si
        result = get_stock_codes_list()
        assert result == ['7203', '8306']

    @patch('update_stocks_price.stocks_info')
    def test_empty_dataframe(self, mock_si_cls):
        mock_si = MagicMock()
        mock_si._fetch_from_jquants.return_value = pd.DataFrame()
        mock_si_cls.return_value = mock_si
        result = get_stock_codes_list()
        assert result == []

    @patch('update_stocks_price.stocks_info')
    def test_none_dataframe(self, mock_si_cls):
        mock_si = MagicMock()
        mock_si._fetch_from_jquants.return_value = None
        mock_si_cls.return_value = mock_si
        result = get_stock_codes_list()
        assert result == []

    @patch('update_stocks_price.stocks_info')
    def test_no_code_column(self, mock_si_cls):
        mock_si = MagicMock()
        mock_si._fetch_from_jquants.return_value = pd.DataFrame({
            'Name': ['Toyota', 'Sony']
        })
        mock_si_cls.return_value = mock_si
        result = get_stock_codes_list()
        assert result == []

    @patch('update_stocks_price.stocks_info')
    def test_5digit_ending_0_trimmed(self, mock_si_cls):
        mock_si = MagicMock()
        mock_si._fetch_from_jquants.return_value = pd.DataFrame({
            'Code': ['72030']
        })
        mock_si_cls.return_value = mock_si
        result = get_stock_codes_list()
        assert result == ['7203']

    @patch('update_stocks_price.stocks_info')
    def test_5digit_not_ending_0_kept(self, mock_si_cls):
        mock_si = MagicMock()
        mock_si._fetch_from_jquants.return_value = pd.DataFrame({
            'Code': ['72031']
        })
        mock_si_cls.return_value = mock_si
        result = get_stock_codes_list()
        assert result == ['72031']

    @patch('update_stocks_price.stocks_info')
    def test_4digit_unchanged(self, mock_si_cls):
        mock_si = MagicMock()
        mock_si._fetch_from_jquants.return_value = pd.DataFrame({
            'Code': ['7203']
        })
        mock_si_cls.return_value = mock_si
        result = get_stock_codes_list()
        assert result == ['7203']


# ===========================================================================
# TestGetFetchDateRange
# ===========================================================================

class TestGetFetchDateRange:
    """日付範囲計算"""

    def test_default_7_days(self):
        from_date, to_date = get_fetch_date_range()
        assert (to_date - from_date).days == 7

    def test_custom_days(self):
        from_date, to_date = get_fetch_date_range(days=30)
        assert (to_date - from_date).days == 30

    def test_to_date_is_midnight(self):
        _, to_date = get_fetch_date_range()
        assert to_date.hour == 0
        assert to_date.minute == 0
        assert to_date.second == 0
        assert to_date.microsecond == 0


# ===========================================================================
# TestMergeWithJquantsPriority
# ===========================================================================

class TestMergeWithJquantsPriority:
    """J-Quants優先マージ"""

    def test_base_none_returns_jquants(self):
        jq_df = _make_price_df(['2024-01-01', '2024-01-02'], [200, 201])
        result = merge_with_jquants_priority(None, jq_df)
        assert len(result) == 2

    def test_base_empty_returns_jquants(self):
        jq_df = _make_price_df(['2024-01-01'], [200])
        result = merge_with_jquants_priority(pd.DataFrame(), jq_df)
        assert len(result) == 1

    def test_no_overlap_concatenates(self):
        base = _make_price_df(['2024-01-01', '2024-01-02'], [100, 101])
        jq = _make_price_df(['2024-01-03', '2024-01-04'], [200, 201])
        result = merge_with_jquants_priority(base, jq)
        assert len(result) == 4

    def test_overlap_jquants_wins(self):
        base = _make_price_df(['2024-01-01'], [100])
        jq = _make_price_df(['2024-01-01'], [200])
        result = merge_with_jquants_priority(base, jq)
        assert len(result) == 1
        assert result['Close'].iloc[0] == 200

    def test_partial_overlap(self):
        base = _make_price_df(['2024-01-01', '2024-01-02', '2024-01-03'], [100, 101, 102])
        jq = _make_price_df(['2024-01-02', '2024-01-03', '2024-01-04'], [200, 201, 202])
        result = merge_with_jquants_priority(base, jq)
        assert len(result) == 4
        # Jan 2, 3 は J-Quants の値（200, 201）
        result_sorted = result.sort_index()
        assert result_sorted['Close'].iloc[1] == 200  # Jan 2
        assert result_sorted['Close'].iloc[2] == 201  # Jan 3

    def test_result_sorted_by_date(self):
        base = _make_price_df(['2024-01-03'], [100])
        jq = _make_price_df(['2024-01-01'], [200])
        result = merge_with_jquants_priority(base, jq)
        assert result.index.is_monotonic_increasing


# ===========================================================================
# TestFetchWithRetry
# ===========================================================================

class TestFetchWithRetry:
    """指数バックオフ付きリトライ"""

    def test_success_first_attempt(self):
        df = pd.DataFrame({'Close': [100]})
        fetch_fn = MagicMock(return_value=df)
        result = _fetch_with_retry(fetch_fn, '7203', datetime.now(), datetime.now())
        assert fetch_fn.call_count == 1
        assert result is df

    @patch('update_stocks_price.time.sleep')
    def test_retry_then_success(self, mock_sleep):
        df = pd.DataFrame({'Close': [100]})
        fetch_fn = MagicMock(side_effect=[Exception("fail"), df])
        result = _fetch_with_retry(fetch_fn, '7203', datetime.now(), datetime.now())
        assert fetch_fn.call_count == 2
        assert result is df
        mock_sleep.assert_called_once_with(1)

    @patch('update_stocks_price.time.sleep')
    def test_max_retries_exhausted(self, mock_sleep):
        fetch_fn = MagicMock(side_effect=Exception("persistent"))
        with pytest.raises(Exception, match="persistent"):
            _fetch_with_retry(fetch_fn, '7203', datetime.now(), datetime.now())
        assert fetch_fn.call_count == 3

    @patch('update_stocks_price.time.sleep')
    def test_exponential_backoff(self, mock_sleep):
        df = pd.DataFrame({'Close': [100]})
        fetch_fn = MagicMock(side_effect=[Exception("1"), Exception("2"), df])
        _fetch_with_retry(fetch_fn, '7203', datetime.now(), datetime.now())
        assert mock_sleep.call_args_list == [call(1), call(2)]


# ===========================================================================
# TestProcessStock
# ===========================================================================

class TestProcessStock:
    """パイプラインConsumer"""

    def _make_sp_mock(self):
        """stocks_price のモックを生成"""
        sp = MagicMock()
        sp._fetch_from_stooq.return_value = None
        sp._fetch_from_jquants.return_value = None
        sp.db.save_stock_prices.return_value = None
        return sp

    @patch('update_stocks_price.time.sleep')
    @patch('update_stocks_price.stocks_price')
    def test_tachibana_and_jquants_success(self, mock_sp_cls, mock_sleep):
        sp = self._make_sp_mock()
        mock_sp_cls.return_value = sp
        tachi_df = _make_price_df(['2024-01-01'], [100])
        jq_df = _make_price_df(['2024-01-01', '2024-01-02'], [200, 201])
        sp._fetch_from_jquants.return_value = jq_df

        code, ok, count, source = process_stock('7203', tachi_df, datetime.now(), datetime.now())
        assert ok is True
        assert source == 'tachibana+jquants'
        sp.db.save_stock_prices.assert_called_once()
        # stooq は呼ばれない
        sp._fetch_from_stooq.assert_not_called()

    @patch('update_stocks_price.time.sleep')
    @patch('update_stocks_price.stocks_price')
    def test_tachibana_success_jquants_fail(self, mock_sp_cls, mock_sleep):
        sp = self._make_sp_mock()
        mock_sp_cls.return_value = sp
        tachi_df = _make_price_df(['2024-01-01'], [100])
        sp._fetch_from_jquants.side_effect = Exception("jquants down")

        code, ok, count, source = process_stock('7203', tachi_df, datetime.now(), datetime.now())
        assert ok is True
        assert source == 'tachibana'

    @patch('update_stocks_price.time.sleep')
    @patch('update_stocks_price.stocks_price')
    def test_stooq_fallback(self, mock_sp_cls, mock_sleep):
        sp = self._make_sp_mock()
        mock_sp_cls.return_value = sp
        stooq_df = _make_price_df(['2024-01-01'], [150])
        jq_df = _make_price_df(['2024-01-01'], [200])
        sp._fetch_from_stooq.return_value = stooq_df
        sp._fetch_from_jquants.return_value = jq_df

        code, ok, count, source = process_stock('7203', None, datetime.now(), datetime.now())
        assert ok is True
        assert source == 'stooq+jquants'

    @patch('update_stocks_price.time.sleep')
    @patch('update_stocks_price.stocks_price')
    def test_all_sources_fail(self, mock_sp_cls, mock_sleep):
        sp = self._make_sp_mock()
        mock_sp_cls.return_value = sp
        sp._fetch_from_stooq.side_effect = Exception("stooq down")
        sp._fetch_from_jquants.side_effect = Exception("jquants down")

        code, ok, count, source = process_stock('7203', None, datetime.now(), datetime.now())
        assert ok is False
        assert count == 0
        assert source is None

    @patch('update_stocks_price.time.sleep')
    @patch('update_stocks_price.stocks_price')
    def test_jquants_always_called(self, mock_sp_cls, mock_sleep):
        sp = self._make_sp_mock()
        mock_sp_cls.return_value = sp
        tachi_df = _make_price_df(['2024-01-01'], [100])
        jq_df = _make_price_df(['2024-01-01'], [200])
        sp._fetch_from_jquants.return_value = jq_df

        process_stock('7203', tachi_df, datetime.now(), datetime.now())
        sp._fetch_from_jquants.assert_called_once()

    @patch('update_stocks_price.time.sleep')
    @patch('update_stocks_price.stocks_price')
    def test_empty_tachibana_triggers_stooq(self, mock_sp_cls, mock_sleep):
        sp = self._make_sp_mock()
        mock_sp_cls.return_value = sp

        process_stock('7203', pd.DataFrame(), datetime.now(), datetime.now())
        sp._fetch_from_stooq.assert_called()


# ===========================================================================
# TestUploadToCloud
# ===========================================================================

class TestUploadToCloud:
    """Cloud アップロード"""

    def test_dry_run_skips_upload(self):
        result = upload_to_cloud(['7203', '8306'], dry_run=True)
        assert result['success'] == ['7203', '8306']
        assert result['failed'] == []

    def test_empty_codes(self):
        result = upload_to_cloud([], dry_run=False)
        assert result == {'success': [], 'failed': []}

    @patch('update_stocks_price.os.path.exists', return_value=True)
    @patch('BackcastPro.api.cloud_run_client.CloudRunClient')
    def test_upload_success(self, mock_client_cls, mock_exists):
        client = mock_client_cls.return_value
        client.config.is_configured.return_value = True
        client.upload_stocks_daily.return_value = True

        result = upload_to_cloud(['7203'])
        assert result['success'] == ['7203']
        assert result['failed'] == []

    @patch('update_stocks_price.os.path.exists', return_value=True)
    @patch('BackcastPro.api.cloud_run_client.CloudRunClient')
    def test_upload_failure(self, mock_client_cls, mock_exists):
        client = mock_client_cls.return_value
        client.config.is_configured.return_value = True
        client.upload_stocks_daily.return_value = False

        result = upload_to_cloud(['7203'])
        assert result['success'] == []
        assert ('7203', 'Upload failed') in result['failed']

    @patch('update_stocks_price.os.path.exists', return_value=True)
    @patch('BackcastPro.api.cloud_run_client.CloudRunClient')
    def test_upload_exception(self, mock_client_cls, mock_exists):
        client = mock_client_cls.return_value
        client.config.is_configured.return_value = True
        client.upload_stocks_daily.side_effect = Exception("network error")

        result = upload_to_cloud(['7203'])
        assert ('7203', 'network error') in result['failed']

    @patch('update_stocks_price.os.path.exists', return_value=False)
    @patch('BackcastPro.api.cloud_run_client.CloudRunClient')
    def test_file_not_found(self, mock_client_cls, mock_exists):
        client = mock_client_cls.return_value
        client.config.is_configured.return_value = True

        result = upload_to_cloud(['7203'])
        assert ('7203', 'File not found') in result['failed']

    @patch('BackcastPro.api.cloud_run_client.CloudRunClient')
    def test_api_not_configured(self, mock_client_cls):
        client = mock_client_cls.return_value
        client.config.is_configured.return_value = False

        result = upload_to_cloud(['7203', '8306'])
        assert len(result['failed']) == 2
        assert all(reason == 'API URL not configured' for _, reason in result['failed'])


# ===========================================================================
# TestMain
# ===========================================================================

class TestMain:
    """main() 統合テスト"""

    @patch('update_stocks_price.upload_to_cloud', return_value={'success': ['7203'], 'failed': []})
    @patch('update_stocks_price.process_stock')
    @patch('update_stocks_price.stocks_price')
    @patch('update_stocks_price.jquants_cls')
    @patch('update_stocks_price.e_api')
    @patch('update_stocks_price.setup_logging')
    def test_main_with_codes(self, mock_log, mock_eapi, mock_jq, mock_sp_cls,
                             mock_process, mock_upload):
        mock_log.return_value = logging.getLogger('test')
        sp = MagicMock()
        mock_sp_cls.return_value = sp
        sp._fetch_from_tachibana.return_value = None

        mock_process.return_value = ('7203', True, 5, 'jquants')

        with patch('sys.argv', ['prog', '--codes', '7203']):
            result = usp.main()

        assert result == 0
        mock_process.assert_called_once()

    @patch('update_stocks_price.get_stock_codes_list', return_value=[])
    @patch('update_stocks_price.setup_logging')
    def test_main_no_codes_returns_1(self, mock_log, mock_codes):
        mock_log.return_value = logging.getLogger('test')
        with patch('sys.argv', ['prog']):
            result = usp.main()
        assert result == 1

    @patch('update_stocks_price.upload_to_cloud', return_value={'success': [], 'failed': [('7203', 'err')]})
    @patch('update_stocks_price.process_stock', return_value=('7203', False, 0, None))
    @patch('update_stocks_price.stocks_price')
    @patch('update_stocks_price.jquants_cls')
    @patch('update_stocks_price.e_api')
    @patch('update_stocks_price.setup_logging')
    def test_main_failures_returns_1(self, mock_log, mock_eapi, mock_jq,
                                     mock_sp_cls, mock_process, mock_upload):
        mock_log.return_value = logging.getLogger('test')
        sp = MagicMock()
        mock_sp_cls.return_value = sp
        sp._fetch_from_tachibana.return_value = None

        with patch('sys.argv', ['prog', '--codes', '7203']):
            result = usp.main()
        assert result == 1


# ===========================================================================
# TestUpdateSummary
# ===========================================================================

class TestUpdateSummary:
    """UpdateSummary データクラス"""

    def test_default_values(self):
        s = UpdateSummary()
        assert s.total_stocks == 0
        assert s.success_count == 0
        assert s.failed_count == 0
        assert s.uploaded == 0
        assert s.upload_failed == 0
        assert s.errors == []
        assert isinstance(s.start_time, datetime)

    def test_error_tracking(self):
        s = UpdateSummary()
        s.errors.append(('7203', 'timeout'))
        assert s.errors == [('7203', 'timeout')]
