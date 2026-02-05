import pandas as pd
import requests
from .util import PRICE_LIMIT_TABLE
try:
    import yfinance as yf
except ImportError:
    yf = None

from datetime import datetime, timedelta
from typing import Tuple

from .jquants import _normalize_columns

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def stooq_daily_quotes(code: str, from_: datetime = None, to: datetime = None) -> pd.DataFrame:
    """
    株価データを取得する（Yahoo Finance API経由）

    Args:
        code (str): 銘柄コード（例: '7203'）
        from_ (datetime): データ取得開始日
        to (datetime): データ取得終了日

    Returns:
        pd.DataFrame: 株価データのDataFrame（DatetimeIndexとして日付がインデックスに設定）
    """
    try:
        # yfinance ライブラリが利用可能な場合はそれを使用
        if yf is not None:
            start = None if from_ is None else from_.strftime('%Y-%m-%d')
            end = None if to is None else to.strftime('%Y-%m-%d')
            df = yf.download(f"{code}.T", start, end, progress=False)
            if not df.empty:
                # データを日付昇順に並び替え
                df = df.sort_index()

                # DatetimeIndexであることを保証
                if not isinstance(df.index, pd.DatetimeIndex):
                    if 'Date' in df.columns:
                        df['Date'] = pd.to_datetime(df['Date'])
                        df = df.set_index('Date')
                    else:
                        df.index = pd.to_datetime(df.index)
                        df.index.name = 'Date'

                return df

        # yfinance が利用できない場合は直接 Yahoo Finance API を使用
        df = _get_yfinance_daily_quotes(code, from_, to)

        if df.empty:
            return pd.DataFrame()

        # データを日付昇順に並び替え
        df = df.sort_index()

        # DatetimeIndexであることを保証（_get_yfinance_daily_quotesは既にDatetimeIndex）
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.set_index('Date')
            else:
                df.index = pd.to_datetime(df.index)
                df.index.name = 'Date'

        return df

    except Exception as e:
        logger.error(f"データ取得中にエラーが発生しました: {e}")
        return pd.DataFrame()


def _stooq_normalize_columns(code: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    カラム名をJ-Quants APIの形式に統一する

    Args:
        df (pd.DataFrame): 元のDataFrame

    Returns:
        pd.DataFrame: カラム名を統一したDataFrame
    """
    # Stooqのカラム名をJ-Quantsの形式にマッピング
    names_mapping = {
        'Open': 'Open',
        'High': 'High', 
        'Low': 'Low',
        'Close': 'Close',
        'Volume': 'Volume',
        "Adj Close": "AdjustmentClose"
    }
    
    return _common_normalize_columns(code, df, names_mapping)


def _common_normalize_columns(code: str, df: pd.DataFrame, names_mapping: dict) -> pd.DataFrame:
    """
    カラム名をJ-Quants APIの形式に統一する（共通処理）

    Args:
        code (str): 銘柄コード
        df (pd.DataFrame): 元のDataFrame
        names_mapping (dict): カラム名のマッピング辞書

    Returns:
        pd.DataFrame: カラム名を統一したDataFrame
    """
    # Dateカラムが存在しない場合、インデックスから作成
    if 'Date' not in df.columns:
        if isinstance(df.index, pd.DatetimeIndex):
            # インデックスが日付の場合は、Dateカラムとして追加
            norm_df = df.copy()
            norm_df['Date'] = norm_df.index
        else:
            # インデックスが日付でない場合は、そのまま使用
            norm_df = df.copy()
            if 'Date' not in norm_df.columns:
                norm_df['Date'] = norm_df.index
    else:
        norm_df = df.copy()
    
    # 必要なカラムのみを選択（Dateカラムは必ず含める）
    column_mapping = {key: value for key, value in names_mapping.items() if key in norm_df.columns}
    
    # Dateカラムを保持しつつ、他のカラムをマッピング
    selected_columns = ['Date'] + [col for col in column_mapping.keys() if col != 'Date']
    norm_df = norm_df[selected_columns].copy()
    norm_df = norm_df.rename(columns=column_mapping)
    
    # 数値フィールドの定義
    numeric_fields = [value for value in column_mapping.values() if value != 'Date']
    
    # DataFrameに存在する数値フィールドのみ変換
    for field in numeric_fields:
        if field in norm_df.columns:
            norm_df[field] = pd.to_numeric(norm_df[field], errors='coerce')

    # Codeカラムを追加
    norm_df['Code'] = code

    # TurnoverValue　| 売買代金（出来高×価格の合計）カラムを追加
    if not 'TurnoverValue' in norm_df.columns:
        norm_df['TurnoverValue'] = norm_df['Volume'] * norm_df['Close']

    # AdjustmentFactor | 株式分割等を考慮した調整係数
    # AdjustmentOpen/High/Low | 調整済価格
    norm_df = _add_adjustment_prices(norm_df)

    # UpperLimit / LowerLimit | 制限値（前日終値を基準に計算）
    norm_df = _add_price_limits(norm_df)

    # 型変換を行う
    norm_df = _normalize_columns(norm_df)
    
    # Dateカラムが存在する場合は、それをインデックスに設定（DatetimeIndexに変換）
    if 'Date' in norm_df.columns:
        # Dateカラムを確実にdatetime型に変換
        date_values = pd.to_datetime(norm_df['Date'], errors='coerce')
        # Dateカラムを更新（変換後の値を使用）
        norm_df['Date'] = date_values
        # Dateカラムをインデックスに設定
        norm_df = norm_df.set_index('Date')
        # インデックスを明示的にDatetimeIndexに変換
        # インデックスが既にDatetimeIndexでない場合に変換
        if not isinstance(norm_df.index, pd.DatetimeIndex):
            norm_df.index = pd.DatetimeIndex(pd.to_datetime(norm_df.index, errors='coerce'))
        # 念のため、再度DatetimeIndexであることを確認
        if not isinstance(norm_df.index, pd.DatetimeIndex):
            # 最終手段：インデックスをDatetimeIndexとして再作成
            norm_df.index = pd.DatetimeIndex(norm_df.index)
    elif isinstance(norm_df.index, pd.DatetimeIndex):
        # Dateカラムがないが、インデックスが既にDatetimeIndexの場合はそのまま使用
        pass
    else:
        # Dateカラムもなく、インデックスもDatetimeIndexでない場合は変換を試みる
        try:
            converted_index = pd.to_datetime(norm_df.index, errors='coerce')
            if converted_index.notna().any():
                norm_df.index = pd.DatetimeIndex(converted_index)
            else:
                import warnings
                warnings.warn("インデックスをDatetimeIndexに変換できませんでした。", stacklevel=2)
        except (ValueError, TypeError) as e:
            import warnings
            warnings.warn(f"インデックスをDatetimeIndexに変換できませんでした: {e}", stacklevel=2)
    
    # 最終確認：インデックスがDatetimeIndexであることを保証
    if not isinstance(norm_df.index, pd.DatetimeIndex) and len(norm_df) > 0:
        # 最終手段として、インデックスを DatetimeIndex に変換を試みる
        try:
            norm_df.index = pd.DatetimeIndex(pd.to_datetime(norm_df.index, errors='coerce'))
        except (ValueError, TypeError):
            import warnings
            warnings.warn(f"最終的なDataFrameのインデックスがDatetimeIndexではありません。型: {type(norm_df.index)}", stacklevel=2)
    
    return norm_df


def _add_adjustment_prices(df: pd.DataFrame) -> pd.DataFrame:
    """
    株式分割等を考慮した調整係数と調整済価格を計算する

    Args:
        df (pd.DataFrame): 元のDataFrame（Open, High, Low, Close, Adj Close を含む）

    Returns:
        pd.DataFrame: 調整係数と調整済価格を追加したDataFrame
    """
    result_df = df.copy()

    # AdjustmentClose が存在しない場合は Close と同じ値を使用
    if not 'AdjustmentClose' in result_df.columns:
        result_df['AdjustmentClose'] = result_df['Close']

    # 調整係数を計算: AdjustmentFactor = Adj Close / Close
    if not 'AdjustmentFactor' in result_df.columns:
        result_df['AdjustmentFactor'] = result_df['AdjustmentClose'] / result_df['Close']
    
    # 調整済価格を計算
    if not 'AdjustmentOpen' in result_df.columns:
        result_df['AdjustmentOpen'] = result_df['Open'] * result_df['AdjustmentFactor']
    if not 'AdjustmentHigh' in result_df.columns:
        result_df['AdjustmentHigh'] = result_df['High'] * result_df['AdjustmentFactor']
    if not 'AdjustmentLow' in result_df.columns:
        result_df['AdjustmentLow'] = result_df['Low'] * result_df['AdjustmentFactor']
    
    # 調整済出来高を計算（株式分割時は出来高も調整が必要）
    if not 'AdjustmentVolume' in result_df.columns:
        result_df['AdjustmentVolume'] = result_df['Volume'] / result_df['AdjustmentFactor']
    
    return result_df


def _add_price_limits(df: pd.DataFrame) -> pd.DataFrame:
    """
    DataFrameに値幅制限（ストップ高・ストップ安）を追加する
    
    Args:
        df: 株価データのDataFrame（'Close'カラムを含む必要がある）
    
    Returns:
        'UpperLimit'と'LowerLimit'カラムを追加したDataFrame
    """

    if 'UpperLimit' in df.columns and 'LowerLimit' in df.columns:
        return df

    def _get_price_limit_range(price: float, expansion: int = 1) -> tuple[float, float]:
        """
        東証の値幅制限（ストップ高・ストップ安）を計算する
        
        Args:
            price: 基準値（通常は前営業日の終値）
            expansion: 値幅制限の拡大倍率（1=通常, 2=2倍, 3=3倍...）
        
        Returns:
            (upper_limit, lower_limit): ストップ高とストップ安の価格のタプル
        
        Raises:
            ValueError: 価格が負の値など無効な場合
        """
        # 東証の値幅制限テーブル: (基準価格の上限, 値幅)
        # 該当する値幅を検索
        for limit_price, width in PRICE_LIMIT_TABLE:
            if price < limit_price:
                adjusted_width = width * expansion
                upper_limit = round(price + adjusted_width, 1)
                lower_limit = round(price - adjusted_width, 1)
                return upper_limit, lower_limit
        
        raise ValueError(f"Invalid price: {price}")

    result_df = df.copy()
    
    # 前日終値を基準に値幅制限を計算
    prev_close = result_df['Close'].shift(1)
    
    # ストップ高・ストップ安を計算（初日はNone）
    def calculate_limits(price):
        if pd.notna(price):
            return _get_price_limit_range(price)
        return None, None
    
    limits = prev_close.apply(calculate_limits)

    if not 'UpperLimit' in result_df.columns:
        result_df['UpperLimit'] = limits.apply(lambda x: x[0])

    if not 'LowerLimit' in result_df.columns:
        result_df['LowerLimit'] = limits.apply(lambda x: x[1])
    
    return result_df


def _get_yfinance_daily_quotes(code: str, from_: datetime = None, to: datetime = None) -> pd.DataFrame:
    """
    Yahoo Finance APIから直接株価データを取得する
    
    Args:
        code (str): 銘柄コード（例: '7203'）
        from_ (datetime): データ取得開始日
        to (datetime): データ取得終了日
    
    Returns:
        pd.DataFrame: 株価データのDataFrame（失敗時は空のDataFrame）
    """
    try:
        # Yahoo Finance APIのURL（.T は東証を表す）
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{code}.T"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # パラメータの設定
        params = {
            'interval': '1d'
        }
        
        # 日付範囲が指定されている場合
        if from_ is not None and to is not None:
            # UNIXタイムスタンプに変換
            params['period1'] = int(from_.timestamp())
            params['period2'] = int(to.timestamp())
        elif from_ is not None:
            params['period1'] = int(from_.timestamp())
            params['period2'] = int(datetime.now().timestamp())
        elif to is not None:
            # 開始日が指定されていない場合、1年前から取得
            params['period1'] = int((to - timedelta(days=365)).timestamp())
            params['period2'] = int(to.timestamp())
        else:
            # 日付範囲が指定されていない場合、デフォルトで1年分
            params['range'] = '1y'
        
        logger.debug(f"Yahoo Finance APIからデータ取得中: {code}.T")
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code != 200:
            logger.warning(f"Yahoo Finance APIからデータ取得失敗: HTTPステータス {response.status_code}")
            return pd.DataFrame()
        
        data = response.json()
        
        # レスポンスの検証
        if 'chart' not in data or 'result' not in data['chart'] or len(data['chart']['result']) == 0:
            logger.warning(f"Yahoo Finance APIからデータが返されませんでした: {code}")
            return pd.DataFrame()
        
        result = data['chart']['result'][0]
        
        # エラーチェック
        if 'error' in result and result['error'] is not None:
            logger.error(f"Yahoo Finance APIエラー: {result['error']}")
            return pd.DataFrame()
        
        # データの抽出
        if 'timestamp' not in result or 'indicators' not in result:
            logger.warning(f"Yahoo Finance APIのレスポンス形式が不正です: {code}")
            return pd.DataFrame()
        
        timestamps = result['timestamp']
        quotes = result['indicators']['quote'][0]
        
        # DataFrameの作成
        df = pd.DataFrame({
            'Date': pd.to_datetime(timestamps, unit='s'),
            'Open': quotes['open'],
            'High': quotes['high'],
            'Low': quotes['low'],
            'Close': quotes['close'],
            'Volume': quotes['volume']
        })
        
        # Dateをインデックスに設定
        df = df.set_index('Date')
        
        # 欠損値を含む行を削除
        df = df.dropna()
        
        # Adj Close が存在する場合は追加
        if 'adjclose' in result['indicators'] and len(result['indicators']['adjclose']) > 0:
            adj_close = result['indicators']['adjclose'][0]['adjclose']
            df['Adj Close'] = adj_close
        else:
            # Adj Close が存在しない場合はCloseと同じ値を使用
            df['Adj Close'] = df['Close']
        
        if df.empty:
            logger.warning(f"Yahoo Finance APIから取得したデータが空でした: {code}")
        else:
            logger.info(f"Yahoo Finance APIからデータ取得成功: {code} ({len(df)}件)")
        
        return df
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Yahoo Finance APIへのリクエスト中にエラーが発生しました: {e}")
        return pd.DataFrame()
    except (KeyError, IndexError, ValueError) as e:
        logger.error(f"Yahoo Finance APIのレスポンス解析中にエラーが発生しました: {e}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Yahoo Finance APIからのデータ取得中に予期しないエラーが発生しました: {e}")
        return pd.DataFrame()
